"""Document-level writing, kept separate from proposal-only render inputs."""

import copy
import hashlib
import json

from api.workspace.models import DocumentDraft
from api.workspace.storage import source_path


def proposal_sections(inputs: dict) -> list[dict]:
    return [s for s in inputs.get("proposal_sections") or []
            if s.get("document_kind", "qualitative_proposal") == "qualitative_proposal"]


def draft_markdown(section: dict) -> str:
    parts = [f"# {section.get('title') or '작성 초안'}", "검토용 초안 · 제출용 승인 아님", section["text"]]
    for ref in section.get("references") or []:
        parts.extend([f"## 회사 참고자료: {ref['name']}", ref["quote"]])
    for ref in section.get("web_references") or []:
        parts.extend([f"## 웹 참고자료 [검증필요]: {ref['title']}", ref["url"], ref["quote"]])
    return "\n\n".join(parts) + "\n"


def save_draft(conn, notice_no: str, body: DocumentDraft) -> None:
    from api.workspace import service

    ws = service.load(conn, notice_no)
    service.assert_source_current(conn, ws)
    inputs = copy.deepcopy(ws["inputs"])
    sections = inputs.setdefault("proposal_sections", [])
    existing = next((s for s in sections if s["id"] == body.draft_id), None)
    payload = body.model_dump(mode="json", exclude={"version", "idempotency_key"})
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    duplicate = next((s for s in sections if s.get("save_key") == body.idempotency_key), None)
    if duplicate:
        if duplicate.get("save_hash") != digest:
            service.fail("idempotency_conflict", "같은 저장 요청의 내용이 변경되었습니다.")
        return
    if ws["version"] != body.version:
        service.fail("version_conflict", "다른 변경사항이 있습니다. 최신 화면을 확인한 뒤 다시 저장하세요.")
    if not body.title.strip() or not body.text.strip():
        service.fail("draft_empty", "서류명과 작성 내용을 입력하세요.", status=422)
    from api.workspace.writing_plan import current

    target = next((item for item in (inputs.get("writing_plan") or {}).get("items", [])
                   if item["id"] == body.draft_id and item["action"] == "write"), None)
    if not current(inputs) or not target:
        service.fail("writing_review_required", "공고 서류 검토에서 실제 작성 대상을 먼저 확인하세요.")
    if target["title"] != body.title or target["document_kind"] != body.document_kind:
        service.fail("writing_target_changed", "서류명과 구분은 공고 서류 검토에서 변경하세요.")
    if existing and not existing.get("document_kind"):
        service.fail("draft_conflict", "기존 요구사항 초안은 서류 확인에서 수정하세요.")
    documents = {d["id"]: d for d in inputs.get("documents", [])}
    references = []
    for ref in body.references:
        doc = documents.get(ref.document_id)
        from api.workspace.asset_policy import document_issue
        eligible = doc and (doc.get("role") == "company_reference" or (
            doc.get("role") in {"company_evidence", "product_evidence"} and doc.get("confirmed")))
        if not eligible or document_issue(doc, inputs.get("company") or {}):
            service.fail("reference_invalid", "이 공고에 등록한 회사 참고자료를 선택하세요.", status=422)
        if not ref.quote.strip() or ref.quote not in (doc.get("text") or ""):
            service.fail("reference_quote_invalid", "발췌문이 회사 참고자료 본문과 일치하지 않습니다.", status=422)
        if doc.get("role") != "company_reference":
            source_path(doc)
        references.append({**ref.model_dump(), "name": doc["name"], "input_version": ws["version"],
                           "role": doc["role"], "sha256": doc.get("sha256"), "approved_as_claim": False})
    section = {
        **(existing or {}), "id": body.draft_id, "document_kind": body.document_kind,
        "title": body.title.strip(), "text": body.text, "review_status": "pending",
        "writing_target": target,
        "requirement_ids": (existing or {}).get("requirement_ids", []),
        "evidence_ids": (existing or {}).get("evidence_ids", []),
        "references": references,
        "web_references": [{**r.model_dump(mode="json"), "verified": False} for r in body.web_references],
        "save_key": body.idempotency_key, "save_hash": digest,
    }
    if existing:
        sections[sections.index(existing)] = section
    else:
        sections.append(section)
    service.change(conn, ws, inputs, "document_draft", body.note)
