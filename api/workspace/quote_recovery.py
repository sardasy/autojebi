"""Source-anchored diagnostics; never turn approximate quotes into accepted facts."""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from api.workspace import service
from api.workspace.errors import WorkspaceError
from api.workspace.models import RequirementRequest
from api.workspace.storage import source_path
from api.workspace.tables import jobs, reviews


class AnalysisFailure(WorkspaceError):
    def __init__(self, result: dict) -> None:
        super().__init__(502, {"code": "unverified_quote",
            "message": "AI 인용 검증에 실패한 항목이 있습니다.",
            "next_action": "항목별 원문 위치를 확인하고 교정한 후보만 채택하세요."})
        self.result = result


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def is_duplicate_requirement(existing: list[dict], document_id: str, quote: str, text: str) -> bool:
    """One rule for adopt, apply and the UI label: same source document and same quote or text."""
    return any(r.get("document_id") == document_id and (r.get("quote") == quote or r.get("text") == text)
               for r in existing)


def matches(text: str, quote: str) -> list[dict]:
    if not quote.strip():
        return []
    exact = [{"start": m.start(), "end": m.start() + len(quote), "quote": quote}
             for m in re.finditer(f"(?={re.escape(quote)})", text)]
    if exact:
        return exact[:50]
    positions = [i for i, char in enumerate(text) if not char.isspace()]
    compact = "".join(text[i] for i in positions)
    needle = "".join(quote.split())
    output = []
    for m in re.finditer(f"(?={re.escape(needle)})", compact):
        start, end = positions[m.start()], positions[m.start() + len(needle) - 1] + 1
        output.append({"start": start, "end": end, "quote": text[start:end]})
        if len(output) == 50:
            break
    return output


def diagnose(items: list, documents: list[dict], version: int) -> list[dict]:
    output = []
    docs = {d["id"]: d for d in documents}
    allowed = {"text", "document_id", "quote", "locator", "category", "mandatory", "specification"}
    for index, item in enumerate(items):
        try:
            if not isinstance(item, dict):
                raise ValueError
            req = RequirementRequest(version=version, **{k: v for k, v in item.items() if k in allowed})
            if req.specification is not None:
                from api.specifications.models import Candidate
                req.specification = Candidate.model_validate(req.specification).model_dump()
        except (ValidationError, ValueError, TypeError):
            output.append({"candidate_id": str(index), "status": "invalid_structure", "matches": []})
            continue
        text = str(docs.get(req.document_id, {}).get("text") or "")
        spans = matches(text, req.quote)
        state = "ambiguous" if len(spans) > 1 else (
            "exact" if spans and spans[0]["quote"] == req.quote else
            "whitespace" if spans else "mismatch")
        output.append({"candidate_id": str(index), "status": state,
                       "requirement": req.model_dump(include=allowed),
                       "source_text_sha256": text_hash(text), "matches": spans})
    return output


def adopt(conn: Any, notice_no: str, job_id: str, body: Any) -> None:
    ws = service.load(conn, notice_no)
    signature = service.digest(body.model_dump(exclude={"version", "idempotency_key"}))
    key = service.digest(body.idempotency_key)
    previous = conn.execute(select(reviews).where(reviews.c.notice_no == notice_no,
        reviews.c.job_id == job_id, reviews.c.action == "adopt_candidates")).mappings().all()
    for review in previous:
        details = review["details"] or {}
        if details.get("key") == key:
            if details.get("signature") != signature:
                service.fail("idempotency_conflict", "같은 요청 키로 다른 내용을 보낼 수 없습니다.")
            return
    ws = service.load(conn, notice_no, body.version)
    service.assert_source_current(conn, ws)
    job = conn.execute(select(jobs).where(jobs.c.id == job_id,
        jobs.c.notice_no == notice_no)).mappings().first()
    if not job or job["kind"] != "analyze" or job["status"] not in {"failed", "succeeded"}:
        service.fail("candidate_unavailable", "채택할 분석 후보가 없습니다.")
    candidates = {c["candidate_id"]: c for c in (job["result"] or {}).get("quote_diagnostics", [])}
    inputs = copy.deepcopy(ws["inputs"])
    seen = set()
    for selected in body.items:
        if selected.candidate_id in seen:
            service.fail("duplicate_candidate", "같은 후보를 중복 선택했습니다.")
        seen.add(selected.candidate_id)
        candidate = candidates.get(selected.candidate_id, {})
        req = candidate.get("requirement")
        if not req:
            service.fail("candidate_unavailable", "유효한 분석 후보가 아닙니다.")
        doc = next((d for d in inputs["documents"] if d["id"] == req["document_id"]
                    and d.get("role") == "notice_source"), None)
        text = str((doc or {}).get("text") or "")
        if not doc or text_hash(text) != candidate.get("source_text_sha256"):
            service.fail("source_changed", "후보의 원문이 변경되었습니다. 다시 대조하세요.")
        source_path(doc)
        quote = selected.quote
        if not quote.strip() or text[selected.start:selected.start + len(quote)] != quote:
            service.fail("unverified_quote", "선택 위치와 원문 인용이 일치하지 않습니다.")
        if is_duplicate_requirement(inputs["requirements"], req["document_id"], quote, req["text"]):
            continue
        inputs["requirements"].append({**req, "id": service.uid(), "quote": quote,
            "source_start": selected.start, "locator": selected.locator,
            "review_status": "pending", "compliance": "unassessed"})
    updated = service.change(conn, ws, inputs, "adopt_requirements", body.note)
    from api.specifications.service import sync_adopted
    sync_adopted(conn, updated)
    service.audit(conn, updated, "adopt_candidates", body.note,
                  {"key": key, "signature": signature}, job_id)
