"""Fill identified slots in a copy of an original notice HWPX, never approve claims."""

from __future__ import annotations

import copy
import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Any

from api.workspace import asset_policy, service
from api.workspace.errors import HANDLED_ERRORS
from api.workspace.forms.hwpx_io import (
    _archive,
    _etree,
    _fields,
    _preview_notice,
    _readback,
    _text,
    _write_text,
)
from api.workspace.forms.schemas import (
    FormFillingRequest,
    FormReference,
    FormReviewRequest,
    FormWebReference,
)
from api.workspace.forms.targets import archive_targets, provenance, resolve, retired
from api.workspace.notice_brief import presentation_free
from api.workspace.readiness_issues import IssueCode, ReadinessIssue, issue, render_blockers
from api.workspace.storage import source_path

WARNINGS = [
    "원본 첨부 양식의 작성 사본이며 제출용 승인 또는 자격증빙이 아닙니다.",
    "한글에서 열어 긴 본문·표·쪽 나눔의 실제 배치를 검토해야 합니다.",
    "미기입 칸은 [확인 필요]이며 서명·주민등록번호·발급 증명서는 자동 작성하지 않습니다.",
    "내장 그림 미리보기는 검토 안내로 교체했으며, 실제 한글 배치 화면이 아닙니다.",
]


def review_basis(inputs: dict) -> str:
    """Review-only actions may advance the version without changing reviewed content."""
    content = presentation_free(inputs)
    content.pop("source_reviewed", None)
    for filling in content.get("form_fillings", []):
        for key in ("review", "review_status", "save_key", "save_hash", "input_version", "note"):
            filling.pop(key, None)
    for section in content.get("proposal_sections", []):
        section.pop("review_status", None)
    return service.digest(content)


def review_filling(conn: Any, notice_no: str, document_id: str, body: FormReviewRequest) -> None:
    ws = service.load(conn, notice_no)
    service.assert_source_current(conn, ws)
    if ws["version"] != body.version:
        service.fail("version_conflict", "입력이 변경되었습니다. 작성본을 다시 확인하세요.")
    _, _, report = export_filling(ws["inputs"], document_id)
    if report["output_sha256"] != body.output_sha256:
        service.fail("form_output_changed", "검토한 작성본과 현재 파일이 다릅니다. 다시 다운로드하세요.")
    if body.approved:
        if not all((body.source_checked, body.content_checked, body.layout_checked)):
            service.fail("form_review_incomplete", "원본·작성 내용과 근거·실제 한글 배치를 모두 확인하세요.", status=422)
        if report["unfilled_count"]:
            service.fail("form_unfilled", "미작성 항목을 채운 뒤 작성본을 다시 검토하세요.")
    inputs = copy.deepcopy(ws["inputs"])
    filling = next(f for f in inputs["form_fillings"] if f["document_id"] == document_id)
    filling["review_status"] = "approved" if body.approved else "rejected"
    filling["review"] = {**body.model_dump(exclude={"version"}),
                         "input_version": ws["version"] + 1,
                         "basis_sha256": review_basis(inputs),
                         "reviewed_at": service.now().isoformat()}
    service.change(conn, ws, inputs, "notice_form_review", body.note)


def _document(inputs: dict, document_id: str) -> dict:
    return resolve(inputs, document_id)


def _source(doc: dict) -> bytes:
    if Path(doc.get("name") or "").suffix.lower() != ".hwpx":
        service.fail("form_unsupported", "원본 HWPX 양식만 자동 기입을 지원합니다.")
    if not re.fullmatch(r"[0-9a-f]{64}", doc.get("sha256") or ""):
        service.fail("form_source_hash_missing", "원본 파일 해시를 먼저 확보하세요.")
    if "_content" in doc:
        content = doc["_content"]
        if hashlib.sha256(content).hexdigest() != doc["sha256"]:
            service.fail("form_source_changed", "내부 파일 해시가 변경되었습니다.")
        return content
    if Path(doc.get("storage_path") or "").is_file() and Path(doc["storage_path"]).stat().st_size > 50_000_000:
        service.fail("form_archive_limit", "원본 양식 크기가 처리 한도를 넘었습니다.")
    path = source_path(doc)
    if path.stat().st_size > 50_000_000:
        service.fail("form_archive_limit", "원본 양식 크기가 처리 한도를 넘었습니다.")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != doc["sha256"]:
        service.fail("form_source_changed", "원본 양식을 읽는 동안 파일 내용이 변경되었습니다.")
    return content


def inspect_document(doc: dict) -> dict:
    result = {"document_id": doc["id"], "name": doc.get("name", ""),
              "sha256": doc.get("sha256"), "supported": False, "fields": [], **provenance(doc)}
    suffix = Path(doc.get("name") or "").suffix.lower()
    if suffix != ".hwpx":
        result["reason"] = ("HWP 바이너리는 수동 작성 대상입니다. 원본 다운로드·본문 추출은 유지됩니다."
                            if suffix == ".hwp" else "PDF·기타 형식은 원본 양식 자동 기입을 지원하지 않습니다.")
        return result
    try:
        content = _source(doc)
        archive, roots = _archive(content)
        with archive:
            result["fields"] = _fields(roots, doc["sha256"])
        result["supported"] = bool(result["fields"])
        if not result["fields"]:
            result["reason"] = "명확한 서식 번호 아래 작성 칸 또는 산출내역서 금액 칸을 찾지 못했습니다. 원문을 검토하세요."
    except HANDLED_ERRORS as exc:
        result["reason"] = (exc.detail.get("message", "원본 양식 확인 실패")
                            if isinstance(exc.detail, dict) else str(exc.detail))
    except (ValueError, KeyError, zipfile.BadZipFile, OSError, SyntaxError) as exc:
        result["reason"] = f"원본 양식을 안전하게 읽을 수 없습니다 ({type(exc).__name__})."
    return result


def inventory(ws: dict) -> dict:
    documents = []
    for doc in ws["inputs"].get("documents", []):
        if doc.get("role") != "notice_source":
            continue
        documents.append(inspect_document(doc))
        if str(doc.get("name", "")).lower().endswith(".zip"):
            try:
                documents.extend(inspect_document(d) for d in archive_targets(
                    doc, str(ws["inputs"].get("notice", {}).get("notice_no") or "")))
            except (*HANDLED_ERRORS, ValueError, OSError, zipfile.BadZipFile):
                documents[-1]["reason"] = "ZIP 경로·해시·압축 한도를 확인하지 못했습니다. 원본 확인 필요"
    return {"version": ws["version"], "documents": documents,
            "retired_fillings": copy.deepcopy([f for f in ws["inputs"].get("form_fillings", [])
                                               if retired(ws["inputs"], f)]),
            "fillings": copy.deepcopy([f for f in ws["inputs"].get("form_fillings", [])
                                       if not retired(ws["inputs"], f)])}


def _reference(ref: FormReference, inputs: dict, version: int) -> dict:
    doc = next((d for d in inputs.get("documents", []) if d["id"] == ref.document_id), None)
    if (not doc or doc.get("role") not in {"company_reference", "company_evidence", "product_evidence"}
            or asset_policy.document_issue(doc, inputs.get("company") or {})):
        service.fail("form_reference_invalid", "이 공고에 등록된 회사·제품 자료를 선택하세요.", status=422)
    if not ref.quote.strip() or ref.quote not in (doc.get("text") or ""):
        service.fail("form_quote_invalid", "발췌문이 등록 자료 본문과 일치하지 않습니다.", status=422)
    if doc.get("storage_path"):
        source_path(doc)
    return {**ref.model_dump(), "name": doc.get("name", ""), "role": doc.get("role"),
            "sha256": doc.get("sha256"), "text_sha256": service.digest(doc.get("text") or ""),
            "input_version": version, "approved_as_claim": False}


def save_filling(conn: Any, notice_no: str, body: FormFillingRequest) -> None:
    ws = service.load(conn, notice_no)
    service.assert_source_current(conn, ws)
    inputs = copy.deepcopy(ws["inputs"])
    payload = body.model_dump(mode="json", exclude={"version", "idempotency_key"})
    digest = service.digest(payload)
    fillings = inputs.setdefault("form_fillings", [])
    duplicate = next((f for f in fillings if f.get("save_key") == body.idempotency_key), None)
    if duplicate:
        if duplicate.get("save_hash") != digest:
            service.fail("idempotency_conflict", "같은 요청 키의 작성 내용이 변경되었습니다.")
        _validate_filling(inputs, duplicate)
        return
    if ws["version"] != body.version:
        service.fail("version_conflict", "입력이 변경되었습니다. 최신 화면을 확인하세요.")
    doc = _document(inputs, body.document_id)
    if doc.get("sha256") != body.source_sha256:
        service.fail("form_source_changed", "원본 양식 해시가 변경되었습니다. 항목을 다시 불러오세요.")
    source = inspect_document(doc)
    if not source["supported"]:
        service.fail("form_unsupported", source.get("reason", "작성 항목이 없습니다."))
    mapping = {f["id"]: f for f in source["fields"]}
    seen, saved = set(), []
    for field in body.fields:
        if field.field_id not in mapping or field.field_id in seen:
            service.fail("form_field_invalid", "원본에 없는 항목 또는 중복 항목입니다.", status=422)
        seen.add(field.field_id)
        if field.value.strip() and not (field.reference or field.web_reference):
            service.fail("form_reference_required", "작성 내용마다 회사 자료 또는 웹 발췌 근거를 연결하세요.", status=422)
        if any(ord(c) < 32 and c not in "\n\r\t" for c in field.value):
            service.fail("form_value_invalid", "양식에 허용되지 않는 제어 문자가 있습니다.", status=422)
        if mapping[field.field_id]["kind"] == "choice" and field.value.strip():
            original = re.sub(r"\([^)]*\)|\s", "", mapping[field.field_id]["original"])
            proposed = re.sub(r"\([^)]*\)|\s", "", field.value)
            choices = re.findall(r"\(([^)]*)\)", field.value)
            if original != proposed or sum(bool(c.strip()) for c in choices) != 1:
                service.fail("form_choice_invalid", "원본 선택 문구를 유지하고 해당 괄호 한 곳에 표시하세요.", status=422)
        if mapping[field.field_id]["kind"] == "amount" and field.value.strip():
            if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?(?:\s*원)?", field.value.strip()):
                service.fail("form_amount_invalid", "금액 칸에는 실제 견적 근거의 숫자를 입력하세요. 미확인 금액은 비워두세요.", status=422)
        item = {"field_id": field.field_id, "value": field.value.replace("\r\n", "\n").replace("\r", "\n"),
                "mapping": mapping[field.field_id]}
        if field.reference:
            item["reference"] = _reference(field.reference, inputs, ws["version"])
        if field.web_reference:
            item["web_reference"] = {**field.web_reference.model_dump(mode="json"), "verified": False}
        saved.append(item)
    filling = {"document_id": body.document_id, "source_sha256": body.source_sha256,
               **provenance(doc),
               "fields": saved, "mapping_sha256": service.digest(source["fields"]),
               "input_version": ws["version"], "review_status": "pending", "note": body.note,
               "save_key": body.idempotency_key, "save_hash": digest}
    prior = next((f for f in fillings if f["document_id"] == body.document_id), None)
    if prior:
        fillings[fillings.index(prior)] = filling
    else:
        fillings.append(filling)
    service.change(conn, ws, inputs, "notice_form_filling", body.note)


def _validate_filling(inputs: dict, filling: dict) -> tuple[dict, dict]:
    doc = _document(inputs, filling["document_id"])
    if provenance(doc) != provenance(filling):
        service.fail("form_target_changed", "작성 대상의 ZIP 출처가 변경되었습니다.")
    if doc.get("sha256") != filling.get("source_sha256"):
        service.fail("form_source_changed", "원본 양식이 변경되어 작성 내용을 다시 확인해야 합니다.")
    source = inspect_document(doc)
    if not source["supported"]:
        service.fail("form_source_unavailable", source.get("reason", "양식 읽기 실패"))
    if service.digest(source["fields"]) != filling.get("mapping_sha256"):
        service.fail("form_mapping_changed", "원본 양식의 작성 위치가 변경되었습니다.")
    mapping = {f["id"]: f for f in source["fields"]}
    for item in filling["fields"]:
        if item.get("mapping") != mapping.get(item["field_id"]):
            service.fail("form_mapping_changed", "저장된 작성 위치가 원본과 일치하지 않습니다.")
        ref = item.get("reference")
        if ref:
            checked = _reference(FormReference(document_id=ref["document_id"], quote=ref["quote"]),
                                 inputs, filling["input_version"])
            if any(checked.get(k) != ref.get(k) for k in ("sha256", "text_sha256", "role")):
                service.fail("form_reference_changed", "작성 근거 자료가 변경되었습니다. 다시 검토하고 저장하세요.")
        web = item.get("web_reference")
        if web:
            FormWebReference.model_validate({k: web[k] for k in ("title", "url", "quote")})
        if item["value"].strip() and not (ref or web):
            service.fail("form_reference_required", "작성 근거가 누락되었습니다.")
    return doc, source


def filling_issues(inputs: dict) -> list[str]:
    return render_blockers(filling_readiness_issues(inputs), deduplicate=True)


def filling_readiness_issues(inputs: dict) -> list[ReadinessIssue]:
    issues = []
    for filling in inputs.get("form_fillings", []):
        if retired(inputs, filling):
            continue
        if filling.get("review_status") != "approved":
            issues.append(issue(IssueCode.FORM_REVIEW_REQUIRED, "form", filling["document_id"]))
            continue
        try:
            _, _, report = export_filling(inputs, filling["document_id"])
            if report["review_status"] != "approved" or report["unfilled_count"]:
                issues.append(issue(IssueCode.FORM_LAYOUT_STALE, "form", filling["document_id"]))
        except (*HANDLED_ERRORS, ValueError, KeyError, OSError):
            issues.append(issue(IssueCode.FORM_REFERENCE_STALE, "form", filling["document_id"]))
    return issues


def export_filling(inputs: dict, document_id: str) -> tuple[bytes, str, dict]:
    filling = next((f for f in inputs.get("form_fillings", [])
                    if f["document_id"] == document_id), None)
    if not filling:
        service.fail("form_filling_missing", "원본 양식 작성 내용을 먼저 저장하세요.", status=404)
    doc, source = _validate_filling(inputs, filling)
    original = _source(doc)
    archive, roots = _archive(original)
    values = {f["field_id"]: f["value"] for f in filling["fields"]}
    changed, expected = set(), []
    with archive:
        for field in source["fields"]:
            member, path = field["location"].split("|", 1)
            root = roots[member]
            targets = root.xpath(path, namespaces={k: v for k, v in root.nsmap.items() if k})
            if len(targets) != 1 or _text(targets[0]) != field["original"]:
                service.fail("form_mapping_changed", "작성 위치의 원본 텍스트가 일치하지 않습니다.")
            value = values.get(field["id"], "").strip()
            if not value:
                value = (field["original"].strip() + " [확인 필요]"
                         if field["kind"] == "choice" else "[확인 필요]")
            _write_text(targets[0], value)
            changed.add(member)
            expected.append((member, path, value))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target:
            target.comment = archive.comment
            for entry in archive.infolist():
                if entry.filename == "Preview/PrvText.txt":
                    content = ("검토용 작성 사본 · 배치 확인 필요\n" + "\n".join(
                        _readback(root) for root in roots.values())).encode("utf-8")
                elif entry.filename == "Preview/PrvImage.png":
                    content = _preview_notice()
                else:
                    content = (_etree().tostring(roots[entry.filename], encoding="UTF-8", xml_declaration=True)
                               if entry.filename in changed else archive.read(entry))
                target.writestr(entry, content)
    result = output.getvalue()
    reopened, read_roots = _archive(result)
    with reopened:
        for member, path, value in expected:
            root = read_roots[member]
            targets = root.xpath(path, namespaces={k: v for k, v in root.nsmap.items() if k})
            if len(targets) != 1 or _readback(targets[0]) != value:
                service.fail("form_readback_failed", "작성된 양식의 저장값 재확인이 실패했습니다.")
    filename = Path(doc["name"]).stem + "_작성사본_검토필요.hwpx"
    filled = sum(bool(values.get(f["id"], "").strip()) for f in source["fields"])
    report = {"source_sha256": doc["sha256"], **provenance(doc), "output_sha256": hashlib.sha256(result).hexdigest(),
              "field_count": len(source["fields"]), "filled_count": filled,
              "unfilled_count": len(source["fields"]) - filled, "review_status": "pending",
              "readback_verified": True, "layout_verified": False, "preview_invalidated": True,
              "warnings": WARNINGS}
    review = filling.get("review") or {}
    current = (review.get("basis_sha256") == review_basis(inputs)
               and review.get("output_sha256") == report["output_sha256"])
    if current:
        report["review_status"] = filling.get("review_status", "pending")
        report["layout_verified"] = bool(review.get("approved") and review.get("layout_checked"))
        report["review"] = review
        if report["review_status"] == "approved" and report["layout_verified"] and not report["unfilled_count"]:
            report["warnings"] = []
            report["notices"] = ["동일 파일의 사람 검토를 기록했습니다. 자격증빙·제출 준비 승인은 별도입니다."]
    return result, filename, report
