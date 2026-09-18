from __future__ import annotations

import copy
import os

from sqlalchemy import select, update

from api.specifications.models import Candidate, Correction, Specification
from api.specifications.tables import active_indexes, generations, spec_events, specifications
from api.specifications.validation import VERSION, sha, validate_spec
from api.workspace import service as workspace
from api.workspace.storage import source_path


def enabled() -> bool:
    return os.getenv("SPEC_SEARCH_ENABLED", "false").lower() == "true" and os.getenv("SPEC_SEARCH_ENV") == "validation"


def require_enabled() -> None:
    if not enabled():
        workspace.fail("spec_search_disabled", "사양 검증 검색은 검증 환경에서만 활성화할 수 있습니다.", status=503)


def etag(row: dict, version: int, index_state: dict | None = None) -> str:
    state = index_state if index_state and index_state.get("latest_generation") else None
    return '"' + workspace.digest({"id": row["id"], "revision": row["revision"], "version": version,
                                    "payload": row["payload"], "normalization": VERSION, "index": state}) + '"'


def document(inputs: dict, document_id: str) -> dict | None:
    return next((d for d in inputs.get("documents", []) if d["id"] == document_id), None)


def verified_evidence(doc: dict | None, inputs: dict) -> bool:
    from api.workspace.asset_policy import document_issue
    doc = doc or {}
    return bool(doc.get("confirmed") and doc.get("company_asset")
        and doc.get("role") in {"company_evidence", "product_evidence"}
        and not document_issue(doc, inputs.get("company") or {}))


def summary(inputs: dict) -> dict:
    from api.workspace.provenance import requirement_valid
    from api.workspace.source_inventory import source_inventory_issues, source_text_complete
    from api.workspace.source_needs import issues
    reqs = [r for r in inputs.get("requirements", []) if r.get("mandatory", True) and r.get("category") == "technical"]
    docs = {d["id"]: d for d in inputs.get("documents", [])}
    source_complete = bool(inputs.get("source_reviewed") and source_text_complete(inputs)
                           and not source_inventory_issues(inputs) and not issues(inputs))
    states = []
    for req in reqs:
        state = req.get("compliance", "unassessed")
        record = inputs.get("specifications", {}).get(req["id"])
        valid = requirement_valid(req, docs)
        if (enabled() or inputs.get("specifications")) and record is None:
            valid = False
        if enabled() or inputs.get("specifications"):
            valid = valid and verified_evidence(docs.get(req.get("evidence_id")), inputs)
        if record:
            check = validate_spec(Specification.model_validate(record["payload"]), docs.get(record["payload"]["source"]["document_id"]))
            valid = valid and check["status"] == "valid" and record["payload"]["source"]["quote"] == req.get("quote") and record["payload"]["source"]["document_id"] == req.get("document_id")
        if state == "does_not_meet":
            states.append(state)
        else:
            states.append(state if valid else "unassessed")
    unresolved = states.count("unassessed")
    state = ("불충족" if "does_not_meet" in states else "미확인" if not source_complete or not states
             or unresolved == len(states) else "일부미확인" if unresolved else "충족")
    return {"spec_compliance": state, "unresolved_spec_count": unresolved, "source_complete": source_complete}


def index_status(conn, ws: dict) -> dict:
    empty = {"active_generation": None, "latest_generation": None, "status": "not_indexed",
             "input_version": None, "current": False}
    if not enabled():
        return {**empty, "status": "disabled"}
    latest = conn.execute(select(generations).where(generations.c.notice_no == ws["notice_no"])
                         .order_by(generations.c.created_at.desc(), generations.c.id).limit(1)).mappings().first()
    active = conn.execute(select(active_indexes.c.generation_id)
                          .where(active_indexes.c.notice_no == ws["notice_no"])).scalar()
    if not latest:
        return empty
    current = latest["input_version"] == ws["version"] and latest["input_hash"] == workspace.digest(ws["inputs"])
    return {"active_generation": active, "latest_generation": latest["id"],
            "status": latest["status"] if current else "stale", "input_version": latest["input_version"],
            "current": current, "stores": latest["stores"]}


def public(row: dict, ws: dict, index_state: dict | None = None) -> dict:
    payload = Specification.model_validate(row["payload"])
    check = validate_spec(payload, document(ws["inputs"], payload.source.document_id))
    return {**dict(row), "validation": check, "etag": etag(row, ws["version"], index_state), "index_state": index_state}


def listing(conn, ws: dict) -> dict:
    rows = conn.execute(select(specifications).where(specifications.c.notice_no == ws["notice_no"])
                        .order_by(specifications.c.id)).mappings().all() if enabled() else []
    state = index_status(conn, ws)
    return {"items": [public(r, ws, state) for r in rows], "input_version": ws["version"], "index_state": state,
            "enabled": enabled(), **summary(ws["inputs"])}


def persist(conn, ws: dict, req_id: str, payload: Specification, note: str) -> dict:
    previous = conn.execute(select(specifications).where(specifications.c.notice_no == ws["notice_no"],
                            specifications.c.requirement_id == req_id)).mappings().first()
    validation = validate_spec(payload, document(ws["inputs"], payload.source.document_id))
    row = {"id": previous["id"] if previous else workspace.uid(), "notice_no": ws["notice_no"],
           "requirement_id": req_id, "revision": previous["revision"] + 1 if previous else 1,
           "input_version": ws["version"], "payload": payload.model_dump(mode="json"),
           "validation": validation, "updated_at": workspace.now()}
    if previous:
        count = conn.execute(update(specifications).where(specifications.c.id == previous["id"],
                    specifications.c.revision == previous["revision"]).values(**row)).rowcount
        if count != 1:
            workspace.fail("spec_conflict", "사양이 변경되었습니다.", status=412)
    else:
        conn.execute(specifications.insert().values(**row))
    conn.execute(spec_events.insert().values(id=workspace.uid(), spec_id=row["id"],
        revision=row["revision"], input_version=ws["version"], payload=row["payload"], validation=validation,
        note=note, created_at=workspace.now()))
    return row


def sync_adopted(conn, ws: dict) -> dict:
    """Called inside an existing audited input change; never run a paid extraction."""
    if not enabled():
        return ws
    inputs = copy.deepcopy(ws["inputs"])
    for req in inputs.get("requirements", []):
        candidate = req.get("specification")
        if not candidate or req["id"] in inputs.get("specifications", {}):
            continue
        doc = document(inputs, req["document_id"])
        quote = req["quote"]
        text = str((doc or {}).get("text") or "")
        if text.count(quote) != 1 or not (doc or {}).get("sha256"):
            continue
        start = text.index(quote)
        payload = Specification(**Candidate.model_validate(candidate).model_dump(), mandatory=req.get("mandatory", True),
            raw=quote, source={"document_id": doc["id"], "document_sha256": doc["sha256"],
                "text_sha256": sha(text), "start": start, "end": start + len(quote), "quote": quote, "locator": req["locator"]})
        row = persist(conn, ws, req["id"], payload, "채택된 사양 후보; 사람 승인 아님")
        inputs.setdefault("specifications", {})[req["id"]] = {"id": row["id"], "revision": row["revision"],
            "payload": row["payload"], "validation": row["validation"]}
    if inputs != ws["inputs"]:
        from api.workspace.tables import workspaces
        conn.execute(update(workspaces).where(workspaces.c.notice_no == ws["notice_no"],
                     workspaces.c.version == ws["version"]).values(inputs=inputs))
    return {**ws, "inputs": inputs}


def correct(conn, notice_no: str, spec_id: str, body: Correction, if_match: str | None) -> dict:
    require_enabled()
    if not if_match:
        workspace.fail("precondition_required", "최신 사양 버전이 필요합니다.", status=428)
    ws = workspace.load(conn, notice_no)
    row = conn.execute(select(specifications).where(specifications.c.id == spec_id,
                        specifications.c.notice_no == notice_no)).mappings().first()
    if not row:
        workspace.fail("spec_not_found", "사양이 없습니다.", status=404)
    if if_match != etag(row, ws["version"], index_status(conn, ws)):
        workspace.fail("spec_conflict", "다른 창에서 변경했습니다. 최신본과 교정본을 비교하세요.", status=412)
    if body.version != ws["version"]:
        workspace.fail("version_conflict", "최신 입력 버전으로 다시 검토하세요.")
    workspace.assert_source_current(conn, ws)
    doc = document(ws["inputs"], body.payload.source.document_id)
    check = validate_spec(body.payload, doc)
    if "source_changed" in check["codes"] or not doc or doc.get("role") != "notice_source":
        workspace.fail("source_changed", "공고 원문과 교정 인용 위치가 일치해야 합니다.")
    source_path(doc)
    inputs = copy.deepcopy(ws["inputs"])
    req = next((r for r in inputs["requirements"] if r["id"] == row["requirement_id"]), None)
    if not req or req["document_id"] != doc["id"] or req["quote"] != body.payload.source.quote:
        workspace.fail("requirement_changed", "연결된 요구사항의 인용부터 교정하세요.")
    req["compliance"] = "unassessed"
    if req.get("review_status") != "rejected":
        req["review_status"] = "pending"
    new = persist(conn, {**ws, "version": ws["version"] + 1}, row["requirement_id"], body.payload, body.note)
    inputs.setdefault("specifications", {})[row["requirement_id"]] = {
        "id": new["id"], "revision": new["revision"], "payload": new["payload"], "validation": check}
    ws = workspace.change(conn, ws, inputs, "spec_correction", body.note)
    return listing(conn, ws)
