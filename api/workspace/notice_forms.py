"""Fill identified slots in a copy of an original notice HWPX, never approve claims."""
from __future__ import annotations

import copy
import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Any

from defusedxml.ElementTree import fromstring as safe_xml
from fastapi import HTTPException
from pydantic import Field, HttpUrl

from api.workspace import service
from api.workspace.attachment_text import checked_archive
from api.workspace.models import StrictModel, VersionRequest

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
FORM = re.compile(r"^[<\[〈【]\s*서식\s*\d+(?:\s*[-–]\s*\d+)?\s*[>\]〉】]$")
PROTECTED = re.compile(r"주민\s*등록|서명|날인|직인|인감|\(\s*인\s*\)|증명서|확인서")
MAX_XML = 8_000_000
WARNINGS = [
    "원본 첨부 양식의 작성 사본이며 제출용 승인 또는 자격증빙이 아닙니다.",
    "한글에서 열어 긴 본문·표·쪽 나눔의 실제 배치를 검토해야 합니다.",
    "미기입 칸은 [확인 필요]이며 서명·주민등록번호·발급 증명서는 자동 작성하지 않습니다.",
    "내장 그림 미리보기는 검토 안내로 교체했으며, 실제 한글 배치 화면이 아닙니다.",
]


class FormReference(StrictModel):
    document_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=12000)


class FormWebReference(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl
    quote: str = Field(min_length=1, max_length=12000)


class FormValue(StrictModel):
    field_id: str = Field(min_length=1, max_length=100)
    value: str = Field(default="", max_length=12000)
    reference: FormReference | None = None
    web_reference: FormWebReference | None = None


class FormFillingRequest(VersionRequest):
    document_id: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=100)
    fields: list[FormValue] = Field(default_factory=list, max_length=200)
    note: str = Field(min_length=1, max_length=2000)


def _etree():
    try:
        from lxml import etree
    except ImportError:
        service.fail("form_dependency_missing", "원본 양식 처리 모듈(lxml)이 설치되지 않았습니다.")
    return etree


def _parse(data: bytes):
    if len(data) > MAX_XML:
        service.fail("form_xml_limit", "양식 XML 크기가 처리 한도를 넘었습니다.")
    # Validate every XML document with DTD/entity prohibitions before preserving its prefixes.
    safe_xml(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    etree = _etree()
    root = etree.fromstring(data, etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False,
        remove_blank_text=False, strip_cdata=False,
    ))
    if sum(1 for _ in root.iter()) > 100000:
        service.fail("form_xml_limit", "양식 XML 요소 수가 처리 한도를 넘었습니다.")
    return root


def _text(node) -> str:
    return "".join(node.itertext())


def _paragraph_text(node) -> str:
    return "".join(_text(t) for t in node.findall("hp:run/hp:t", NS))


def _archive(content: bytes):
    archive = checked_archive(content)
    try:
        if archive.read("mimetype").strip() != b"application/hwp+zip":
            service.fail("invalid_hwpx", "HWPX 원본 형식을 확인할 수 없습니다.")
        if any("signature" in name.lower() for name in archive.namelist()):
            service.fail("signed_hwpx", "전자서명된 원본 양식은 수정하지 않습니다.")
        roots = {}
        for entry in archive.infolist():
            if entry.filename.lower().endswith((".xml", ".hpf", ".rdf")):
                root = _parse(archive.read(entry))
                if re.fullmatch(r"Contents/section\d+\.xml", entry.filename):
                    roots[entry.filename] = root
        if not roots:
            service.fail("invalid_hwpx", "HWPX 본문 섹션이 없습니다.")
        return archive, roots
    except Exception:
        archive.close()
        raise


def _candidate(fields: list[dict], root, member: str, sha256: str,
               node, label: str, context: str, kind: str) -> None:
    if (not label.strip() or PROTECTED.search(re.sub(r"\s", "", label))
            or PROTECTED.search(re.sub(r"\s", "", context))):
        return
    if len(fields) >= 200:
        service.fail("form_field_limit", "양식 항목 수가 처리 한도를 넘었습니다.")
    location = member + "|" + root.getroottree().getpath(node)
    fields.append({
        "id": "form-" + hashlib.sha256((sha256 + "|" + location).encode()).hexdigest()[:32],
        "label": label.strip(), "context": context.strip(), "original": _text(node),
        "location": location, "kind": kind,
    })


def _fields(roots: dict, sha256: str) -> list[dict]:
    fields: list[dict] = []
    context, heading, item_label = "", "", ""
    for member, root in sorted(roots.items()):
        for paragraph in root.findall("hp:p", NS):
            plain = _paragraph_text(paragraph).strip()
            if FORM.fullmatch(plain):
                context, heading, item_label = plain, "", ""
                continue
            if not context:
                continue
            if plain and not heading and len(plain) < 100 and not re.match(r"20\d\d\s*\.", plain):
                heading = plain
            if not heading:
                title_tables = paragraph.findall(".//hp:tbl", NS)
                if title_tables and len(_text(title_tables[0]).strip()) < 100:
                    heading = _text(title_tables[0]).strip()
            full_context = f"{context} {heading}".strip()
            if re.fullmatch(r"항목\s*\d+\s*[.．]?", plain):
                item_label = plain
            if (item_label and "작성지침" in plain and "자유롭게" in plain
                    and len(plain) < 300):
                _candidate(fields, root, member, sha256, paragraph,
                           item_label, full_context, "paragraph")
                item_label = ""
            elif re.fullmatch(r"20\d\d\s*\.\s*00\s*\.\s*00\s*\.?", plain):
                _candidate(fields, root, member, sha256, paragraph,
                           "작성일자", full_context, "date")
            for table in paragraph.findall(".//hp:tbl", NS):
                if any(ancestor.tag == f"{{{HP}}}tbl" for ancestor in table.iterancestors()):
                    continue
                for row in table.findall("hp:tr", NS):
                    previous_label = ""
                    for cell in row.findall("hp:tc", NS):
                        text = " ".join(_paragraph_text(p).strip()
                                        for p in cell.findall("hp:subList/hp:p", NS)).strip()
                        if text:
                            previous_label = text
                            if re.search(r"\(\s*\)", text) and len(text) < 120:
                                _candidate(fields, root, member, sha256, cell,
                                           text, full_context, "choice")
                            continue
                        if cell.find(".//hp:tbl", NS) is not None:
                            continue
                        span = cell.find("hp:cellSpan", NS)
                        colspan = int(span.get("colSpan", "1")) if span is not None else 1
                        label = previous_label
                        if not label and colspan >= 3 and "연혁" in full_context:
                            label = "주요연혁"
                        if label:
                            _candidate(fields, root, member, sha256, cell,
                                       label, full_context, "cell")
    known = {field["id"] for field in fields}
    fields.extend(field for field in _cost_fields(roots, sha256) if field["id"] not in known)
    return fields


def _cost_fields(roots: dict, sha256: str) -> list[dict]:
    """Explicit bill-of-costs only: never infer editable prices from specification tables."""
    fields: list[dict] = []
    for member, root in roots.items():
        titles = {re.sub(r"\s", "", _paragraph_text(p)) for p in root.findall("hp:p", NS)}
        if not titles.intersection({"산출내역서", "산출공내역서", "공내역서"}):
            continue
        for table in root.findall(".//hp:tbl", NS):
            if any(a.tag == f"{{{HP}}}tbl" for a in table.iterancestors()):
                continue
            rows = table.findall("hp:tr", NS)
            if not rows or len(rows) > 100:
                continue
            header = {}
            for cell in rows[0].findall("hp:tc", NS):
                addr = cell.find("hp:cellAddr", NS)
                span = cell.find("hp:cellSpan", NS)
                label = re.sub(r"\s", "", _text(cell))
                if addr is not None and (span is None or span.get("colSpan", "1") == "1"):
                    header[label] = int(addr.get("colAddr", "-1"))
            if not {"품명", "수량", "단가", "금액"}.issubset(header):
                continue
            if len({header[k] for k in ("품명", "수량", "단가", "금액")}) != 4:
                continue
            for row in rows[1:]:
                cells = {}
                for cell in row.findall("hp:tc", NS):
                    addr = cell.find("hp:cellAddr", NS)
                    if addr is not None:
                        cells[int(addr.get("colAddr", "-1"))] = cell
                cell_texts = {column: _text(cell).strip() for column, cell in cells.items()}
                item = cell_texts.get(header["품명"], "")
                quantity = cell_texts.get(header["수량"], "")
                summary = re.sub(r"\s", "", cell_texts.get(header["단가"], ""))
                if item and re.fullmatch(r"[1-9]\d*(?:\.\d+)?", quantity):
                    targets = [(header[k], f"{item[:160]} · {k}") for k in ("단가", "금액")]
                    context = f"산출내역서 · 원본 수량 {quantity} · 자동 가격 계산 없음"
                elif summary in {"공급가액", "부가가치세", "부가세", "합계", "총계"}:
                    targets = [(header["금액"], summary)]
                    context = "산출내역서 · 합산/세액은 실제 견적 근거로 입력"
                else:
                    continue
                for column, label in targets:
                    cell = cells.get(column)
                    if cell is None or cell_texts.get(column) or cell.find(".//hp:tbl", NS) is not None:
                        continue
                    span = cell.find("hp:cellSpan", NS)
                    if span is not None and any(span.get(k, "1") != "1" for k in ("rowSpan", "colSpan")):
                        continue
                    _candidate(fields, root, member, sha256, cell, label, context, "amount")
    return fields


def _document(inputs: dict, document_id: str) -> dict:
    doc = next((d for d in inputs.get("documents", []) if d["id"] == document_id), None)
    if not doc or doc.get("role") != "notice_source":
        service.fail("form_source_missing", "공고에 연결된 원본 양식을 선택하세요.", status=404)
    return doc


def _source(doc: dict) -> bytes:
    from api.workspace.execution import source_path
    if Path(doc.get("name") or "").suffix.lower() != ".hwpx":
        service.fail("form_unsupported", "원본 HWPX 양식만 자동 기입을 지원합니다.")
    if not re.fullmatch(r"[0-9a-f]{64}", doc.get("sha256") or ""):
        service.fail("form_source_hash_missing", "원본 파일 해시를 먼저 확보하세요.")
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
              "sha256": doc.get("sha256"), "supported": False, "fields": []}
    suffix = Path(doc.get("name") or "").suffix.lower()
    if suffix != ".hwpx":
        result["reason"] = ("HWP 원본은 한글 Worker 기반 원본 양식 기입이 필요합니다."
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
    except HTTPException as exc:
        result["reason"] = (exc.detail.get("message", "원본 양식 확인 실패")
                            if isinstance(exc.detail, dict) else str(exc.detail))
    except (ValueError, KeyError, zipfile.BadZipFile, OSError, SyntaxError) as exc:
        result["reason"] = f"원본 양식을 안전하게 읽을 수 없습니다 ({type(exc).__name__})."
    return result


def inventory(ws: dict) -> dict:
    return {"version": ws["version"], "documents": [inspect_document(d)
            for d in ws["inputs"].get("documents", []) if d.get("role") == "notice_source"],
            "fillings": copy.deepcopy(ws["inputs"].get("form_fillings", []))}


def _reference(ref: FormReference, inputs: dict, version: int) -> dict:
    from api.workspace.asset_policy import document_issue
    from api.workspace.execution import source_path
    doc = next((d for d in inputs.get("documents", []) if d["id"] == ref.document_id), None)
    if (not doc or doc.get("role") not in {"company_reference", "company_evidence", "product_evidence"}
            or document_issue(doc, inputs.get("company") or {})):
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
    issues = []
    for filling in inputs.get("form_fillings", []):
        try:
            _validate_filling(inputs, filling)
        except (HTTPException, ValueError, KeyError):
            issues.append("원본 양식 작성 근거 또는 위치 재검토 필요")
        issues.append("원본 양식 작성 사본의 실제 배치·내용 검토 미완료")
    return list(dict.fromkeys(issues))


def _write_text(node, value: str) -> None:
    etree = _etree()
    paragraphs = [node] if node.tag == f"{{{HP}}}p" else node.findall("hp:subList/hp:p", NS)
    if not paragraphs:
        service.fail("form_slot_invalid", "작성 칸의 원본 문단이 없습니다.")
    paragraph = paragraphs[0]
    runs = paragraph.findall("hp:run", NS)
    if not runs:
        service.fail("form_slot_invalid", "작성 칸의 원본 글자 서식이 없습니다.")
    for p in paragraphs:
        for t in p.findall("hp:run/hp:t", NS):
            t.text = None
            for child in list(t):
                t.remove(child)
        # Line geometry is computed content cache; retain style/paragraph/table properties.
        for segments in p.findall("hp:linesegarray", NS):
            p.remove(segments)
    first = runs[0].find("hp:t", NS)
    if first is None:
        first = etree.SubElement(runs[0], f"{{{HP}}}t")
    parts = value.split("\n")
    first.text = parts[0]
    for part in parts[1:]:
        etree.SubElement(first, f"{{{HP}}}lineBreak").tail = part


def _readback(node) -> str:
    output = []
    for t in node.findall(".//hp:t", NS):
        output.append(t.text or "")
        for child in t:
            if child.tag == f"{{{HP}}}lineBreak":
                output.append("\n")
            output.append(child.tail or "")
    return "".join(output)


def _preview_notice() -> bytes:
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (600, 240), "#f4f6fa")
    ImageDraw.Draw(image).multiline_text(
        (35, 65), "REVIEW COPY\n\nOpen the HWPX in Hangul to review layout.\nNot approved for submission.",
        fill="#1d3557", spacing=8,
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


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
    report = {"source_sha256": doc["sha256"], "output_sha256": hashlib.sha256(result).hexdigest(),
              "field_count": len(source["fields"]), "filled_count": filled,
              "unfilled_count": len(source["fields"]) - filled, "review_status": "pending",
              "readback_verified": True, "layout_verified": False, "preview_invalidated": True,
              "warnings": WARNINGS}
    return result, filename, report
