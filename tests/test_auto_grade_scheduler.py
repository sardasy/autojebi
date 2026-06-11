"""_grade_job 자동 grade 스케줄러 잡 테스트 (M5)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from api.collector import scheduler
from api.routers.notices import bid_pipeline, metadata


@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    return engine


def _seed(engine, *, notice_no, status, graded_at=None):
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no=notice_no,
                title=f"t-{notice_no}",
                source="G2B",
                raw={},
                category="ABB장비",
                fit_score=0,
                assignee="이용문",
                analysis={},
                status=status,
                created_at=now,
                updated_at=now,
                graded_at=graded_at,
            )
        )


def test_grade_job_returns_early_when_db_missing(monkeypatch, caplog):
    """DATABASE_URL 미설정 시 조용히 return (raise 안함)."""
    from api.db import MissingDatabaseUrl

    def boom():
        raise MissingDatabaseUrl("DATABASE_URL not set")

    monkeypatch.setattr(scheduler, "get_engine", boom)
    scheduler._grade_job()  # raise 없음 확인


def test_grade_job_no_candidates(sqlite_engine, monkeypatch):
    """analyzed AND graded_at IS NULL 공고가 없으면 no-op."""
    _seed(sqlite_engine, notice_no="A", status="collected")  # 후보 아님
    _seed(
        sqlite_engine,
        notice_no="B",
        status="analyzed",
        graded_at=datetime.now(tz=UTC),
    )  # 이미 graded

    monkeypatch.setattr(scheduler, "get_engine", lambda: sqlite_engine)

    called = {"n": 0}

    def fake_impl(*args, **kwargs):
        called["n"] += 1

    monkeypatch.setattr("api.services.grading_runner.grade_notice_impl", fake_impl)
    scheduler._grade_job()
    assert called["n"] == 0


def test_grade_job_calls_impl_per_candidate(sqlite_engine, monkeypatch):
    _seed(sqlite_engine, notice_no="A", status="analyzed")
    _seed(sqlite_engine, notice_no="B", status="analyzed")

    monkeypatch.setattr(scheduler, "get_engine", lambda: sqlite_engine)
    from api.config import settings

    monkeypatch.setattr(settings, "grade_batch_limit", 50)

    called_notices: list[str] = []

    def fake_impl(engine, notice_no, *, alert=True):
        called_notices.append(notice_no)
        result = MagicMock()
        result.score_total = 0.7
        result.slack_delivered = False
        return result

    monkeypatch.setattr("api.services.grading_runner.grade_notice_impl", fake_impl)
    scheduler._grade_job()
    assert sorted(called_notices) == ["A", "B"]


def test_grade_job_continues_after_failure(sqlite_engine, monkeypatch):
    _seed(sqlite_engine, notice_no="A", status="analyzed")
    _seed(sqlite_engine, notice_no="B", status="analyzed")
    _seed(sqlite_engine, notice_no="C", status="analyzed")

    monkeypatch.setattr(scheduler, "get_engine", lambda: sqlite_engine)
    from api.config import settings

    monkeypatch.setattr(settings, "grade_batch_limit", 50)

    processed: list[str] = []

    def fake_impl(engine, notice_no, *, alert=True):
        processed.append(notice_no)
        if notice_no == "B":
            raise RuntimeError("transient failure")
        result = MagicMock()
        result.score_total = 0.7
        result.slack_delivered = False
        return result

    monkeypatch.setattr("api.services.grading_runner.grade_notice_impl", fake_impl)
    scheduler._grade_job()
    # B 실패해도 A, C는 처리됨
    assert sorted(processed) == ["A", "B", "C"]


def test_grade_job_respects_batch_limit(sqlite_engine, monkeypatch):
    for i in range(5):
        _seed(sqlite_engine, notice_no=f"N-{i}", status="analyzed")

    monkeypatch.setattr(scheduler, "get_engine", lambda: sqlite_engine)
    from api.config import settings

    monkeypatch.setattr(settings, "grade_batch_limit", 2)

    called: list[str] = []

    def fake_impl(engine, notice_no, *, alert=True):
        called.append(notice_no)
        result = MagicMock()
        result.score_total = 0.5
        result.slack_delivered = False
        return result

    monkeypatch.setattr("api.services.grading_runner.grade_notice_impl", fake_impl)
    scheduler._grade_job()
    # 5개 후보 중 batch_limit=2만큼만
    assert len(called) == 2
