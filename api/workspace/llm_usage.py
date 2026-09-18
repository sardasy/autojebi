"""Durable per-content call reservations and exact-request result reuse."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update

from api.workspace.models import RequirementRequest
from api.workspace.provenance import evidence_valid, source_quote_valid
from api.workspace.providers import configured_key
from api.workspace.service import digest, fail, load
from api.workspace.tables import budgets, jobs

_BOOKKEEPING = {
    "created_at",
    "updated_at",
    "uploaded_at",
    "extracted_at",
    "reviewed_at",
    "storage_path",
    "file_path",
    "local_path",
    "path",
}
_REQUIREMENT_FIELDS = (
    "id",
    "text",
    "document_id",
    "quote",
    "locator",
    "category",
    "mandatory",
    "proposed_value",
    "evidence_id",
    "evidence_quote",
    "evidence_locator",
    "proposal_disposition",
    "proposal_note",
)


def _content(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _content(v) for k, v in value.items() if k not in _BOOKKEEPING}
    if isinstance(value, list):
        return [_content(v) for v in value]
    return value


def source_input_key(snapshot: dict) -> str:
    # IDs, names, classification and approval are bindings, not new source content.
    # Keep complete bodies and original-byte checksums, never excerpts alone.
    documents = [
        {k: d.get(k) for k in ("sha256", "text", "text_excerpt", "original_body", "original_text")}
        for d in snapshot.get("documents") or []
    ]
    company = {
        k: v
        for k, v in (snapshot.get("company") or {}).items()
        if k not in {"id", "active", "version"}
    }
    return digest(
        {
            "format": "workspace-source-v1",
            "notice": _content(snapshot.get("notice") or {}),
            "raw": _content(snapshot.get("raw") or {}),
            "company": _content(company),
            "documents": sorted({digest(d) for d in documents}),
        }
    )


def proposal_requirements(snapshot: dict) -> list[dict]:
    return [
        {k: r[k] for k in _REQUIREMENT_FIELDS if k in r} for r in snapshot.get("requirements") or []
    ]


def _snapshot_known(snapshot: Any) -> bool:
    return (
        isinstance(snapshot, dict)
        and all(isinstance(snapshot.get(k), dict) for k in ("notice", "company", "raw"))
        and isinstance(snapshot.get("documents"), list)
        and all(isinstance(d, dict) for d in snapshot["documents"])
    )


def _reconcile(conn: Any, notice_no: str, rows: list[dict]) -> None:
    """Attach only unambiguous historical snapshots; unknown usage stays a debit."""
    if not any(r["input_key"] is None for r in rows):
        return
    history = (
        conn.execute(
            select(jobs.c.input_version, jobs.c.snapshot).where(
                jobs.c.notice_no == notice_no,
                jobs.c.kind.in_(["analyze", "proposal"]),
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        if row["input_key"] is not None:
            continue
        snapshots = [h["snapshot"] for h in history if h["input_version"] == row["input_version"]]
        if not snapshots or not all(_snapshot_known(s) for s in snapshots):
            continue
        keys = {source_input_key(s) for s in snapshots}
        if len(keys) == 1:
            row["input_key"] = keys.pop()
            conn.execute(
                update(budgets)
                .where(
                    budgets.c.notice_no == notice_no,
                    budgets.c.input_version == row["input_version"],
                    budgets.c.input_key.is_(None),
                )
                .values(input_key=row["input_key"])
            )


def reserve_call(engine: Any, job: dict) -> None:
    """Reserve before dispatch; failures/unknown provider outcomes are never refunded."""
    if not configured_key():
        fail(
            "llm_not_configured",
            "LLM 인증이 등록되지 않았습니다.",
            "로컬 .env에 선택한 공급자의 API 키를 등록하고 API와 작업 실행기를 재시작하세요.",
        )
    exhausted = False
    with engine.begin() as conn:
        # The workspace row serializes reservations even across different versions.
        ws = load(conn, job["notice_no"], job["input_version"])
        snapshot = job.get("snapshot", ws["inputs"])
        key = source_input_key(snapshot)
        if key != source_input_key(ws["inputs"]):
            fail("version_conflict", "작업 원문과 현재 입력이 일치하지 않습니다.")
        rows = [
            dict(r)
            for r in conn.execute(
                select(budgets).where(
                    budgets.c.notice_no == job["notice_no"],
                )
            ).mappings()
        ]
        _reconcile(conn, job["notice_no"], rows)
        used = sum(r["calls"] for r in rows if r["input_key"] in {None, key})
        row = next((r for r in rows if r["input_version"] == job["input_version"]), None)
        if row and row["input_key"] not in {None, key}:
            fail("version_conflict", "같은 입력 버전에 다른 원문이 등록되어 있습니다.")
        if used >= 2:
            exhausted = True
        elif row:
            conn.execute(
                update(budgets)
                .where(
                    budgets.c.notice_no == job["notice_no"],
                    budgets.c.input_version == job["input_version"],
                )
                .values(calls=row["calls"] + 1)
            )
        else:
            conn.execute(
                budgets.insert().values(
                    notice_no=job["notice_no"],
                    input_version=job["input_version"],
                    input_key=key,
                    calls=1,
                )
            )
    # Commit reconciliation even when the reservation is denied.
    if exhausted:
        fail("llm_budget_exhausted", "동일 원문·회사·증빙 내용의 LLM 호출 한도 2회에 도달했습니다.")


def result_metadata(job: dict, request: dict) -> dict:
    key = source_input_key(job["snapshot"])
    return {
        "input_key": key,
        "operation_key": digest(
            {
                "format": "workspace-llm-v1",
                "kind": job["kind"],
                "input_key": key,
                "request": request,
            }
        ),
        "model": request["model"],
        "provider": request.get("provider", "anthropic"),
        "reused_from_job_id": None,
    }


def _valid_result(kind: str, result: dict, snapshot: dict) -> bool:
    documents = {d["id"]: d for d in snapshot.get("documents") or []}
    try:
        if kind == "analyze":
            items = result.get("requirements")
            return bool(
                isinstance(items, list)
                and items
                and all(
                    source_quote_valid(RequirementRequest(version=1, **r).model_dump(), documents)
                    for r in items
                )
            )
        requirements = {r["id"]: r for r in snapshot.get("requirements") or []}
        sections = result.get("sections")
        if not isinstance(sections, list) or not sections:
            return False
        for section in sections:
            if not isinstance(section, dict):
                return False
            req_ids, ev_ids = section.get("requirement_ids"), section.get("evidence_ids")
            if not (
                isinstance(section.get("text"), str)
                and section["text"].strip()
                and isinstance(req_ids, list)
                and req_ids
                and isinstance(ev_ids, list)
                and ev_ids
                and all(k in requirements for k in req_ids)
                and all(
                    k in documents
                    and documents[k].get("confirmed")
                    and documents[k].get("role") in {"company_evidence", "product_evidence"}
                    and documents[k].get("text")
                    for k in ev_ids
                )
            ):
                return False
            for key in req_ids:
                req = requirements[key]
                if not source_quote_valid(req, documents):
                    return False
                if req.get("evidence_id") and (
                    req["evidence_id"] not in ev_ids or not evidence_valid(req, documents)
                ):
                    return False
        return True
    except (KeyError, TypeError, ValueError, ValidationError):
        return False


def reuse_result(engine: Any, job: dict, request: dict) -> dict | None:
    kind, snapshot = job["kind"], job["snapshot"]
    metadata = result_metadata(job, request)
    with engine.begin() as conn:
        ws = load(conn, job["notice_no"], job["input_version"])
        if source_input_key(ws["inputs"]) != metadata["input_key"]:
            fail("version_conflict", "작업 원문과 현재 입력이 일치하지 않습니다.")
        candidates = conn.execute(
            select(jobs)
            .where(
                jobs.c.notice_no == job["notice_no"],
                jobs.c.kind == kind,
                jobs.c.status == "succeeded",
            )
            .order_by(jobs.c.created_at.desc())
        ).mappings()
        for previous in candidates:
            result = previous["result"]
            if not isinstance(result, dict):
                continue
            stored = result.get("llm_usage") or {}
            if not isinstance(stored, dict):
                continue
            if (
                stored.get("operation_key") != metadata["operation_key"]
                or stored.get("input_key") != metadata["input_key"]
                or source_input_key(previous["snapshot"]) != metadata["input_key"]
                or not _valid_result(kind, result, snapshot)
            ):
                continue
            reused = deepcopy(result)
            reused["llm_usage"] = {**metadata, "reused_from_job_id": previous["id"]}
            return reused
    return None
