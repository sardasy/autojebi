"""Opt-in real PostgreSQL queue tests; never target a production database."""

import os
import threading
import time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError

from api.routers.notices import bid_pipeline
from api.workspace.models import JobRequest, ReviewRequest
from api.workspace.service import enqueue, initialize, now, review_artifact, uid
from api.workspace.tables import jobs, reviews
from api.workspace.worker import run_once

URL = os.getenv("WORKSPACE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="requires isolated PostgreSQL _check DB")


def test_postgres_serializes_two_workers_and_persists_jobs(monkeypatch):
    assert URL.rsplit("/", 1)[-1].endswith("_check"), "test DB name must end in _check"
    engine = create_engine(URL)
    no = "E2E-QUEUE-" + uid()
    with engine.begin() as conn:
        conn.execute(
            bid_pipeline.insert().values(
                notice_no=no,
                title="Queue regression",
                source="E2E",
                raw={},
                category="비관련",
                fit_score=0,
                assignee="미배정",
                analysis={},
                status="collected",
                created_at=now(),
                updated_at=now(),
            )
        )
        initialize(conn, no)
        one = enqueue(conn, no, JobRequest(kind="excel", input_version=1, idempotency_key="one"))
        two = enqueue(conn, no, JobRequest(kind="notify", input_version=1, idempotency_key="two"))
    calls, errors = [], []
    active = threading.Event()

    def execute(_engine, job):
        calls.append(job["id"])
        active.set()
        time.sleep(0.25)
        return {"warnings": []}

    monkeypatch.setattr("api.workspace.worker.execute", execute)

    def first():
        try:
            run_once(engine)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=first)
    thread.start()
    assert active.wait(5)
    assert run_once(engine) is False
    thread.join(5)
    assert not thread.is_alive() and not errors
    assert run_once(engine)
    with engine.connect() as conn:
        rows = conn.execute(select(jobs).where(jobs.c.notice_no == no)).mappings().all()
    assert {r["id"] for r in rows} == {one["id"], two["id"]}
    assert all(r["status"] == "succeeded" for r in rows)
    assert len(calls) == 2
    engine.dispose()


def seed_workspace(engine):
    no = "E2E-RECOVERY-" + uid()
    with engine.begin() as conn:
        conn.execute(
            bid_pipeline.insert().values(
                notice_no=no,
                title="Postgres recovery",
                source="E2E",
                raw={},
                category="비관련",
                fit_score=0,
                assignee="미배정",
                analysis={},
                status="collected",
                created_at=now(),
                updated_at=now(),
            )
        )
        initialize(conn, no)
        job = enqueue(conn, no, JobRequest(kind="excel", input_version=1, idempotency_key="one"))
    return no, job


def test_postgres_completion_retries_commit_without_duplicate_execution(monkeypatch, tmp_path):
    assert URL.rsplit("/", 1)[-1].endswith("_check")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    engine = create_engine(URL)
    _, job = seed_workspace(engine)
    from api.workspace import worker

    original_execute = worker.execute
    calls, failures = [], []

    def execute(*args):
        calls.append(args[1]["id"])
        return original_execute(*args)

    def interrupt(_conn, _cursor, statement, parameters, _context, _many):
        if (
            statement.startswith("UPDATE workspace_jobs")
            and isinstance(parameters, dict)
            and parameters.get("status") == "succeeded"
            and len(failures) < 2
        ):
            failures.append(1)
            raise OperationalError(
                "completion-write", {}, RuntimeError("simulated transient database failure")
            )

    monkeypatch.setattr(worker, "execute", execute)
    event.listen(engine, "before_cursor_execute", interrupt)
    try:
        assert run_once(engine)
        assert calls == [job["id"]] and len(failures) == 2
        with engine.connect() as conn:
            assert (
                conn.execute(select(jobs.c.status).where(jobs.c.id == job["id"])).scalar_one()
                == "succeeded"
            )
    finally:
        event.remove(engine, "before_cursor_execute", interrupt)
        engine.dispose()


def test_postgres_concurrent_reviews_reject_stale_window(monkeypatch, tmp_path):
    assert URL.rsplit("/", 1)[-1].endswith("_check")
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    engine = create_engine(URL)
    no, job = seed_workspace(engine)
    assert run_once(engine)
    barrier = threading.Barrier(2)
    outcomes = []

    def review(action):
        barrier.wait(timeout=5)
        try:
            with engine.begin() as conn:
                review_artifact(
                    conn,
                    no,
                    ReviewRequest(
                        version=1,
                        job_id=job["id"],
                        action=action,
                        note="Concurrent review",
                        expected_review_id=None,
                    ),
                )
            outcomes.append("saved")
        except HTTPException as exc:
            outcomes.append(exc.detail["code"])

    threads = [
        threading.Thread(target=review, args=(action,)) for action in ("approved", "rejected")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert sorted(outcomes) == ["review_conflict", "saved"]
    with engine.connect() as conn:
        assert len(conn.execute(select(reviews).where(reviews.c.job_id == job["id"])).all()) == 1
    engine.dispose()
