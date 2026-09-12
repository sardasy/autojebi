"""Isolated SQLite fault injection; PostgreSQL lock/concurrency validation is separate."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.exc import OperationalError

from api.routers.notices import bid_pipeline, metadata
from api.workspace import receipts, service, worker
from api.workspace.models import JobRequest
from api.workspace.tables import jobs, workspaces


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("HWP_TEMPLATE_ROOT", str(tmp_path / "templates"))
    monkeypatch.setattr(worker, "RETRY_DELAY", 0)


@pytest.fixture
def queued(sqlite_engine):
    return seed_job(sqlite_engine)


def seed_job(engine):
    with engine.begin() as conn:
        conn.execute(
            bid_pipeline.insert().values(
                notice_no="RECOVERY",
                title="Recovery",
                source="TEST",
                raw={},
                category="test",
                fit_score=0,
                assignee="test",
                analysis={},
                status="collected",
                created_at=service.now(),
                updated_at=service.now(),
            )
        )
        service.initialize(conn, "RECOVERY")
        return service.enqueue(
            conn,
            "RECOVERY",
            JobRequest(
                kind="hwp",
                input_version=1,
                idempotency_key="one",
            ),
        )


def row(engine, job_id):
    with engine.connect() as conn:
        return dict(conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one())


def db_failure():
    return OperationalError("SECRET SQL", {"token": "SECRET TOKEN"}, Exception("SECRET PROVIDER"))


def spy_execute(monkeypatch, action=None):
    calls = []

    def execute(engine, job):
        calls.append(job["id"])
        if action:
            action(engine, job)
        return {"artifact": "result.hwp", "sha256": "test", "warnings": []}

    monkeypatch.setattr(worker, "execute", execute)
    return calls


def fail_updates(engine, count):
    attempts = []

    def inject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE workspace_jobs") and "result=" in statement:
            attempts.append(statement)
            if len(attempts) <= count:
                raise db_failure()

    event.listen(engine, "before_cursor_execute", inject)
    return attempts, inject


def test_completion_update_retries_without_reexecuting(sqlite_engine, queued, monkeypatch):
    calls = spy_execute(monkeypatch)
    attempts, listener = fail_updates(sqlite_engine, 2)
    try:
        assert worker.run_once(sqlite_engine)
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", listener)
    done = row(sqlite_engine, queued["id"])
    assert len(attempts) == 3 and calls == [queued["id"]]
    assert done["status"] == "succeeded" and done["result"]["artifact"] == "result.hwp"
    assert done["claim_token"] is None and done["lease_until"] is None
    assert not receipts.pending()
    assert receipts.read_health()["last_failure"]["code"] == "completion_pending"


def test_exhaustion_leaves_receipt_and_recovers_before_expiry(sqlite_engine, queued, monkeypatch):
    calls = spy_execute(monkeypatch)
    attempts, listener = fail_updates(sqlite_engine, 100)
    try:
        with pytest.raises(OperationalError):
            worker.run_once(sqlite_engine)
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", listener)
    assert len(attempts) == worker.COMPLETION_ATTEMPTS
    assert row(sqlite_engine, queued["id"])["status"] == "running"
    saved = receipts.read(receipts.pending()[0])
    assert saved.job_id == queued["id"] and saved.claim_token
    assert saved.input_version == 1 and saved.result["artifact"] == "result.hwp"
    with sqlite_engine.begin() as conn:
        conn.execute(update(jobs).values(lease_until=service.now() - timedelta(hours=1)))
    assert worker.run_once(sqlite_engine, receipts.RuntimeHealth())
    assert row(sqlite_engine, queued["id"])["status"] == "succeeded"
    assert calls == [queued["id"]] and not receipts.pending()


@pytest.mark.parametrize("after_commit", [False, True])
def test_crash_after_receipt_or_commit_replays_once(
    sqlite_engine, queued, monkeypatch, after_commit
):
    calls = spy_execute(monkeypatch)
    original = worker.persist_completion

    def crash(conn, receipt):
        if after_commit:
            original(conn, receipt)
        raise SystemExit(99)

    monkeypatch.setattr(worker, "persist_completion", crash)
    with pytest.raises(SystemExit):
        worker.run_once(sqlite_engine)
    assert len(receipts.pending()) == 1
    before = row(sqlite_engine, queued["id"])
    monkeypatch.setattr(worker, "persist_completion", original)
    assert worker.run_once(sqlite_engine, receipts.RuntimeHealth())
    done = row(sqlite_engine, queued["id"])
    assert done["status"] == "succeeded" and calls == [queued["id"]]
    if after_commit:
        assert done == before
    assert not receipts.pending()


def test_process_restart_recovers_without_reexecuting(tmp_path):
    database = tmp_path / "restart.sqlite"
    engine = create_engine("sqlite:///" + database.as_posix())
    metadata.create_all(engine)
    job = seed_job(engine)
    script = """
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from api.workspace import worker, receipts

engine = create_engine("sqlite:///" + Path(sys.argv[1]).as_posix())
def execute(engine, job):
    artifact = receipts.data_root() / "once.hwp"
    with artifact.open("xb") as stream:
        stream.write(b"simulated HWP output")
    return {"artifact": str(artifact), "warnings": []}
worker.execute = execute
if sys.argv[2] == "crash":
    save = receipts.save
    def crash(receipt):
        save(receipt)
        os._exit(73)
    receipts.save = crash
assert worker.run_once(engine)
"""
    try:
        first = subprocess.run(
            [sys.executable, "-c", script, str(database), "crash"],
            capture_output=True,
            timeout=30,
        )
        assert first.returncode == 73
        assert row(engine, job["id"])["status"] == "running"
        assert len(receipts.pending()) == 1
        second = subprocess.run(
            [sys.executable, "-c", script, str(database), "recover"],
            capture_output=True,
            timeout=30,
        )
        assert second.returncode == 0
        done = row(engine, job["id"])
        assert done["status"] == "succeeded" and done["result"]["artifact"].endswith("once.hwp")
        assert not receipts.pending()
    finally:
        engine.dispose()


def test_commit_acknowledgement_failure_is_idempotent(sqlite_engine, queued, monkeypatch):
    calls = spy_execute(monkeypatch)
    original = worker.persist_completion
    attempts = []

    def persist(conn, receipt):
        original(conn, receipt)
        attempts.append(1)
        if len(attempts) == 1:
            raise db_failure()

    monkeypatch.setattr(worker, "persist_completion", persist)
    assert worker.run_once(sqlite_engine)
    assert row(sqlite_engine, queued["id"])["status"] == "succeeded"
    assert len(attempts) == 2 and calls == [queued["id"]]


def test_failed_recovery_prevents_claim_or_expiry(sqlite_engine, queued, monkeypatch):
    calls = spy_execute(monkeypatch)
    attempts, listener = fail_updates(sqlite_engine, 100)
    try:
        with pytest.raises(OperationalError):
            worker.run_once(sqlite_engine)
        with sqlite_engine.begin() as conn:
            conn.execute(update(jobs).values(lease_until=service.now() - timedelta(hours=1)))
        before = row(sqlite_engine, queued["id"])
        monkeypatch.setattr(worker, "claim", lambda _: pytest.fail("claim before recovery"))
        with pytest.raises(OperationalError):
            worker.run_once(sqlite_engine)
        assert row(sqlite_engine, queued["id"]) == before
        assert len(attempts) == 2 * worker.COMPLETION_ATTEMPTS
        assert calls == [queued["id"]] and len(receipts.pending()) == 1
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", listener)


@pytest.mark.parametrize(
    "change,code", [("version", "version_conflict"), ("source", "source_changed")]
)
def test_completion_revalidates_in_update_transaction(
    sqlite_engine,
    queued,
    monkeypatch,
    change,
    code,
):
    calls = spy_execute(monkeypatch)
    attempts, listener = fail_updates(sqlite_engine, 1)
    original = worker.persist_completion
    count = 0

    def persist(conn, receipt):
        nonlocal count
        count += 1
        if count == 2:
            with sqlite_engine.begin() as mutation:
                mutation.execute(
                    update(workspaces).values(version=2)
                    if change == "version"
                    else update(bid_pipeline).values(title="Changed")
                )
        original(conn, receipt)

    checked = []
    original_load = worker.load
    original_source = worker.assert_source_current

    def load(conn, *args):
        assert conn.in_transaction()
        checked.append(conn)
        return original_load(conn, *args)

    def source(conn, ws):
        assert conn.in_transaction()
        return original_source(conn, ws)

    def update_gate(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE workspace_jobs") and "result=" in statement:
            assert conn is checked[-1] and conn.in_transaction()

    monkeypatch.setattr(worker, "persist_completion", persist)
    monkeypatch.setattr(worker, "load", load)
    monkeypatch.setattr(worker, "assert_source_current", source)
    event.listen(sqlite_engine, "before_cursor_execute", update_gate)
    try:
        assert worker.run_once(sqlite_engine)
    finally:
        event.remove(sqlite_engine, "before_cursor_execute", listener)
        event.remove(sqlite_engine, "before_cursor_execute", update_gate)
    done = row(sqlite_engine, queued["id"])
    assert done["status"] == "blocked" and done["error"]["code"] == code
    assert done["quality"] is None and done["result"]["artifact"] == "result.hwp"
    assert len(attempts) == 2 and calls == [queued["id"]]


@pytest.mark.parametrize("fence", ["token", "version", "terminal"])
def test_stale_receipt_cannot_overwrite_new_claim(sqlite_engine, queued, monkeypatch, fence):
    calls = spy_execute(monkeypatch)
    original = worker.complete
    monkeypatch.setattr(worker, "complete", lambda *args: (_ for _ in ()).throw(SystemExit(99)))
    with pytest.raises(SystemExit):
        worker.run_once(sqlite_engine)
    values = {"claim_token": service.uid(), "result": {"newer": True}}
    if fence == "version":
        values = {"input_version": 2, "result": {"newer": True}}
    elif fence == "terminal":
        values = {"status": "failed", "result": {"newer": True}}
    with sqlite_engine.begin() as conn:
        conn.execute(update(jobs).values(**values))
    before = row(sqlite_engine, queued["id"])
    monkeypatch.setattr(worker, "complete", original)
    assert worker.run_once(sqlite_engine)
    assert row(sqlite_engine, queued["id"]) == before
    assert calls == [queued["id"]] and not receipts.pending()


@pytest.mark.parametrize("payload", [b"{SECRET", b"\xff", b"[]", b'{"schema_version": 99}'])
def test_malformed_receipts_quarantined_without_logging(
    sqlite_engine,
    queued,
    monkeypatch,
    payload,
    capsys,
):
    calls = spy_execute(monkeypatch)
    directory = receipts.data_root() / "receipts"
    directory.mkdir(parents=True)
    (directory / "malformed.json").write_bytes(payload)
    assert worker.run_once(sqlite_engine)
    assert len(list((directory / "quarantine").iterdir())) == 1
    assert calls == [queued["id"]] and not receipts.pending()
    health = receipts.read_health()
    assert health["last_failure"]["code"] == "invalid_receipt"
    assert "SECRET" not in json.dumps(health) + capsys.readouterr().out + capsys.readouterr().err


def test_atomic_write_preserves_previous_receipt_on_replace_failure(
    sqlite_engine, queued, monkeypatch
):
    job = worker.claim(sqlite_engine)
    receipt = receipts.Receipt(
        job_id=job["id"],
        claim_token=job["claim_token"],
        notice_no=job["notice_no"],
        input_version=1,
        status="succeeded",
        result={"old": True},
        error=None,
        completed_at=service.now(),
    )
    path = receipts.save(receipt)
    original = path.read_bytes()

    def fail(*args):
        raise OSError("SECRET filesystem path")

    monkeypatch.setattr(receipts.os, "replace", fail)
    with pytest.raises(OSError):
        receipts.save(receipt.model_copy(update={"result": {"new": True}}))
    assert path.read_bytes() == original
    assert not list(path.parent.glob("*.tmp"))


def test_lost_session_never_reconnects_for_completion(monkeypatch):
    calls = []

    def persist(*args):
        calls.append(1)
        raise db_failure()

    monkeypatch.setattr(worker, "persist_completion", persist)
    with pytest.raises(OperationalError):
        worker.complete(SimpleNamespace(invalidated=True), None, receipts.RuntimeHealth())
    assert calls == [1]


def test_recovery_holds_advisory_lock_and_precedes_claim(monkeypatch):
    order = []

    class Gate:
        invalidated = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, statement):
            order.append("lock" if "try_advisory" in str(statement) else "unlock")
            return SimpleNamespace(scalar=lambda: True)

        def commit(self):
            pass

        def rollback(self):
            pass

    gate = Gate()
    engine = SimpleNamespace(connect=lambda: gate, dialect=SimpleNamespace(name="postgresql"))
    monkeypatch.setattr(worker, "recover", lambda *args: order.append("recover"))
    monkeypatch.setattr(worker, "claim", lambda *args: order.append("claim"))
    worker.run_once(engine)
    assert order == ["lock", "recover", "claim", "unlock"]


def test_unlock_failure_discards_session(monkeypatch):
    invalidated = []

    class Gate:
        invalidated = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, statement):
            if "pg_advisory_unlock" in str(statement):
                raise db_failure()
            return SimpleNamespace(scalar=lambda: True)

        def commit(self):
            pass

        def rollback(self):
            pass

        def invalidate(self):
            invalidated.append(True)

    engine = SimpleNamespace(connect=lambda: Gate(), dialect=SimpleNamespace(name="postgresql"))
    monkeypatch.setattr(worker, "claim", lambda *args: None)
    with pytest.raises(OperationalError):
        worker.run_once(engine)
    assert invalidated == [True]
    assert receipts.read_health()["last_failure"]["code"] == "unlock_failure"


def test_main_survives_database_errors_and_retains_sanitized_failure(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["worker"])
    monkeypatch.setattr(
        worker,
        "get_engine",
        lambda: SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"),
        ),
    )
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)
    calls = []

    def run(*args):
        calls.append(1)
        if len(calls) < 3:
            raise db_failure()
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "run_once", run)
    with pytest.raises(KeyboardInterrupt):
        worker.main()
    health = receipts.read_health()
    assert len(calls) == 3 and health["state"] == "stopped"
    assert health["last_failure"]["code"] == "database_failure"
    restarted = receipts.RuntimeHealth()
    restarted.record("idle")
    assert receipts.read_health()["last_failure"] == health["last_failure"]
    output = capsys.readouterr()
    assert "SECRET" not in json.dumps(health) + output.out + output.err


def test_heartbeat_advances_during_execution(monkeypatch):
    health = receipts.RuntimeHealth()
    written = threading.Event()
    original = health.record
    count = []

    def record(*args):
        original(*args)
        count.append(receipts.read_health()["heartbeat_at"])
        if len(count) >= 2:
            written.set()

    monkeypatch.setattr(health, "record", record)
    original_wait = health._stop.wait
    monkeypatch.setattr(health._stop, "wait", lambda _: original_wait(0.01))
    health.start()
    try:
        assert written.wait(2)
        assert count[0] != count[1]
    finally:
        health.stop()
