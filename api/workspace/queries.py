"""Workspace reads/writes used by the HTTP layer (moved out of ``api.routers.workspace``, R2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from api.db.tables import bid_pipeline
from api.workspace import service
from api.workspace.tables import jobs, workspaces

PAGE_SIZE = 20


def workspace_exists(conn: Any, notice_no: str) -> bool:
    return bool(
        conn.execute(
            select(workspaces.c.notice_no).where(workspaces.c.notice_no == notice_no)
        ).first()
    )


def notice_exists(conn: Any, notice_no: str) -> bool:
    return bool(
        conn.execute(
            select(bid_pipeline.c.notice_no).where(bid_pipeline.c.notice_no == notice_no)
        ).first()
    )


def lock_notice(conn: Any, notice_no: str) -> None:
    """Lock the notice row so simultaneous initialization stays idempotent."""
    conn.execute(
        select(bid_pipeline.c.notice_no)
        .where(bid_pipeline.c.notice_no == notice_no)
        .with_for_update()
    )


def list_notices(conn: Any, q: str, page: int) -> dict:
    query = select(bid_pipeline.c.notice_no, bid_pipeline.c.title).order_by(
        bid_pipeline.c.updated_at.desc()
    )
    if q:
        query = query.where(
            bid_pipeline.c.title.contains(q, autoescape=True)
            | bid_pipeline.c.notice_no.contains(q, autoescape=True)
        )
    rows = conn.execute(
        query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1)
    ).mappings().all()
    output = []
    for row in rows[:PAGE_SIZE]:
        ws = service.view(conn, row["notice_no"]) if workspace_exists(conn, row["notice_no"]) else None
        output.append({**row, "workspace": ws.model_dump(mode="json") if ws else None})
    return {"items": output, "page": page, "has_more": len(rows) > PAGE_SIZE}


def get_job(conn: Any, job_id: str) -> dict:
    row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
    if not row:
        service.fail("job_not_found", "작업 기록이 없습니다.", status=404)
    return dict(row)


def record_blocked_attempt(conn: Any, notice_no: str, body: Any, detail: dict) -> dict | None:
    """Persist a rejected HWP request as a blocked job and return the error detail with its id.

    Returns ``None`` when the attempt is not recorded (non-HWP kinds or no workspace yet).
    """
    if body.kind not in {"hwp", "hwp_inspect"} or not workspace_exists(conn, notice_no):
        return None
    ws = service.load(conn, notice_no)
    attempted = service.create_job_record(
        conn,
        ws,
        body.kind,
        "blocked:" + service.uid(),
        {
            "template_key": body.template_key,
            "attempt_only": True,
            "requested_input_version": body.input_version,
            "request_key_hash": service.digest(body.idempotency_key),
        },
    )
    detail = {**detail, "job_id": attempted["id"]}
    conn.execute(
        update(jobs)
        .where(jobs.c.id == attempted["id"])
        .values(status="blocked", error=detail, finished_at=service.now())
    )
    return detail


def latest_inspection(conn: Any, notice_no: str, version: int, template_key: str) -> dict | None:
    inspections = conn.execute(select(jobs.c.result, jobs.c.parameters).where(
        jobs.c.notice_no == notice_no, jobs.c.input_version == version,
        jobs.c.kind == "hwp_inspect", jobs.c.status == "succeeded",
    ).order_by(jobs.c.created_at.desc())).mappings()
    return next((row["result"] for row in inspections
                 if row["parameters"].get("template_key") == template_key), None)


def recent_checks(conn: Any, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        select(jobs.c.kind, jobs.c.status, jobs.c.finished_at)
        .where(jobs.c.kind.in_(["analyze", "hwp"]), jobs.c.finished_at.is_not(None))
        .order_by(jobs.c.finished_at.desc())
        .limit(limit)
    ).mappings().all()
    return [dict(r) for r in rows]
