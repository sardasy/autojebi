"""Run separately: python -m api.workspace.worker [--once]. Never starts in API."""

from __future__ import annotations

import argparse
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.exc import (
    DBAPIError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
    TimeoutError,
)

from api.db import get_engine
from api.workspace import receipts
from api.workspace.errors import HANDLED_ERRORS, HandledError
from api.workspace.executors import execute
from api.workspace.lanes import LOCAL_KINDS, validate_lane
from api.workspace.service import assert_source_current, load, now, uid
from api.workspace.tables import jobs

COMPLETION_ATTEMPTS = 3
RETRY_DELAY = 0.25
ADVISORY_LOCK = 71420831


def claim(engine: Any, lane: str = "all") -> dict | None:
    validate_lane(lane)
    lane_filter = (jobs.c.kind.in_(LOCAL_KINDS) if lane == "local" else
                   jobs.c.kind.not_in(LOCAL_KINDS) if lane == "external" else True)
    stamp = now()
    with engine.begin() as conn:
        conn.execute(
            update(jobs)
            .where(jobs.c.status == "running", jobs.c.lease_until < stamp, lane_filter)
            .values(
                status="failed",
                finished_at=stamp,
                error={
                    "code": "interrupted",
                    "message": "실행 프로세스가 중단되어 결과 확인이 필요합니다.",
                    "next_action": "생성 파일과 Worker 실행 상태 확인 후 다시 요청하세요.",
                },
                claim_token=None,
            )
        )
        row = (
            conn.execute(
                select(jobs)
                .where(jobs.c.status == "queued", lane_filter)
                .order_by(jobs.c.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        token = uid()
        changed = conn.execute(
            update(jobs)
            .where(jobs.c.id == row["id"], jobs.c.status == "queued")
            .values(
                status="running",
                claim_token=token,
                started_at=stamp,
                lease_until=stamp + timedelta(minutes=20),
            )
        ).rowcount
        return {**row, "claim_token": token} if changed else None


def persist_completion(conn: Any, receipt: receipts.Receipt) -> None:
    """Commit the version/source gate and fenced completion on the lock-owning session."""
    with conn.begin():
        identity = (
            jobs.c.id == receipt.job_id,
            jobs.c.notice_no == receipt.notice_no,
            jobs.c.input_version == receipt.input_version,
            jobs.c.status == "running",
            jobs.c.claim_token == receipt.claim_token,
        )
        if not conn.execute(select(jobs.c.id).where(*identity)).first():
            return
        status, error = receipt.status, receipt.error
        try:
            ws = load(conn, receipt.notice_no, receipt.input_version)
            assert_source_current(conn, ws)
        except HANDLED_ERRORS as exc:
            status, error = http_failure(exc)
        if error is not None:
            error = {**error, "job_id": receipt.job_id}
        conn.execute(
            update(jobs)
            .where(*identity)
            .values(
                status=status,
                result=receipt.result,
                error=error,
                quality=(
                    "warning" if receipt.result and receipt.result.get("warnings") else "normal"
                )
                if status == "succeeded"
                else None,
                finished_at=receipt.completed_at,
                claim_token=None,
                lease_until=None,
            )
        )


def transient(exc: SQLAlchemyError) -> bool:
    return isinstance(exc, OperationalError | InterfaceError | TimeoutError) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    )


def complete(conn: Any, receipt: receipts.Receipt, health: receipts.RuntimeHealth) -> None:
    health.record("persisting")
    for attempt in range(COMPLETION_ATTEMPTS):
        try:
            persist_completion(conn, receipt)
            return
        except SQLAlchemyError as exc:
            health.record("retrying", "completion_pending")
            # Reconnecting would lose the session lock. Leave the receipt for the next loop.
            if conn.invalidated or not transient(exc) or attempt == COMPLETION_ATTEMPTS - 1:
                raise
            time.sleep(RETRY_DELAY * (2**attempt))


def recover(conn: Any, health: receipts.RuntimeHealth, lane: str = "all") -> bool:
    recovered = False
    health.record("recovering")
    for path in receipts.pending(lane):
        try:
            receipt = receipts.read(path)
            if receipt.lane != lane:
                raise ValueError("wrong_receipt_lane")
        except ValueError:
            receipts.quarantine(path)
            health.record(failure="invalid_receipt")
            continue
        complete(conn, receipt, health)
        receipts.remove(path)
        recovered = True
    return recovered


def http_failure(exc: HandledError) -> tuple[str, dict]:
    return (
        "blocked" if exc.status_code < 500 else "failed",
        exc.detail
        if isinstance(exc.detail, dict)
        else {
            "code": "blocked",
            "message": "입력을 확인할 수 없습니다.",
            "next_action": "입력을 확인하세요.",
        },
    )


def run_once(engine: Any, health: receipts.RuntimeHealth | None = None, lane: str = "all") -> bool:
    validate_lane(lane)
    health = health or receipts.RuntimeHealth(lane)
    # A session lock spans COM/file operations, not just a transaction or HTTP request.
    with engine.connect() as gate:
        postgres = engine.dialect.name == "postgresql"
        lock_id = ADVISORY_LOCK if lane == "all" else ADVISORY_LOCK + (1 if lane == "local" else 2)
        shared = False
        if postgres:
            try:
                if lane != "all":
                    shared = gate.execute(text(f"SELECT pg_try_advisory_lock_shared({ADVISORY_LOCK})")).scalar()
                    gate.commit()
                    if not shared:
                        return False
                acquired = gate.execute(
                    text(f"SELECT pg_try_advisory_lock({lock_id})")
                ).scalar()
                gate.commit()
            except SQLAlchemyError:
                gate.invalidate()
                raise
            if not acquired:
                if shared:
                    gate.execute(text(f"SELECT pg_advisory_unlock_shared({ADVISORY_LOCK})"))
                    gate.commit()
                return False
        try:
            recovered = recover(gate, health) if lane == "all" else recover(gate, health, lane)
            job = claim(engine) if lane == "all" else claim(engine, lane)
            if not job:
                health.record("idle")
                return recovered
            result, error, status = None, None, "succeeded"
            health.record("executing")
            try:
                with engine.begin() as conn:
                    ws = load(conn, job["notice_no"], job["input_version"])
                    assert_source_current(conn, ws)
                result = execute(engine, job)
            except HANDLED_ERRORS as exc:
                status, error = http_failure(exc)
                from api.workspace.quote_recovery import AnalysisFailure
                if isinstance(exc, AnalysisFailure):
                    result = exc.result
            except Exception:
                # Provider exceptions can contain tokens and source text. Do not persist them.
                status = "failed"
                error = {
                    "code": "execution_failed",
                    "message": "작업을 완료하지 못했습니다. 이전 정상 결과는 유지됩니다.",
                    "next_action": "연결 설정과 입력 파일을 확인하세요.",
                }
            if error is not None:
                error = {**error, "job_id": job["id"]}
            receipt = receipts.Receipt(
                job_id=job["id"],
                claim_token=job["claim_token"],
                notice_no=job["notice_no"],
                input_version=job["input_version"],
                status=status,
                result=result,
                error=error,
                completed_at=now(),
                lane=lane,
            )
            path = receipts.save(receipt)
            complete(gate, receipt, health)
            receipts.remove(path)
            health.record("idle")
            return True
        finally:
            if postgres:
                if gate.invalidated:
                    health.record("retrying", "database_failure")
                else:
                    try:
                        gate.rollback()
                        gate.execute(text(f"SELECT pg_advisory_unlock({lock_id})"))
                        if shared:
                            gate.execute(text(f"SELECT pg_advisory_unlock_shared({ADVISORY_LOCK})"))
                        gate.commit()
                    except SQLAlchemyError:
                        # Never return a possibly locked session to the connection pool.
                        gate.invalidate()
                        health.record("retrying", "unlock_failure")
                        raise


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(".env", override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--lane", choices=["all", "local", "external"], default="all")
    args = parser.parse_args()
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise SystemExit("Durable worker requires PostgreSQL; SQLite is test-only.")
    if args.lane != "all" and receipts.pending():
        raise SystemExit("Recover legacy completion receipts before starting split workers.")
    health = receipts.RuntimeHealth() if args.lane == "all" else receipts.RuntimeHealth(args.lane)
    health.start()
    try:
        while True:
            try:
                ran = run_once(engine, health) if args.lane == "all" else run_once(engine, health, args.lane)
            except Exception as exc:
                failure = (
                    "database_failure"
                    if isinstance(exc, SQLAlchemyError)
                    else ("storage_failure" if isinstance(exc, OSError) else "runtime_failure")
                )
                health.record("retrying", failure)
                if args.once:
                    raise SystemExit(1) from None
                time.sleep(1)
                continue
            if args.once:
                return
            if not ran:
                time.sleep(1)
    finally:
        health.stop()


if __name__ == "__main__":
    main()
