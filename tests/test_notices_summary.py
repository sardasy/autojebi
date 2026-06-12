from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import insert

from api.routers.notices import bid_pipeline


def _seed_notice(
    engine,
    *,
    notice_no: str,
    status: str,
    close_date: datetime | None = None,
    graded_at: datetime | None = None,
    analysis: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no=notice_no,
                title=f"notice {notice_no}",
                source="G2B",
                raw={},
                category="비분류",
                fit_score=0,
                assignee="미배정",
                analysis=analysis or {},
                status=status,
                created_at=now,
                updated_at=now,
                close_date=close_date,
                graded_at=graded_at,
            )
        )


def test_notice_summary_empty_db(client):
    r = client.get("/notices/summary")

    assert r.status_code == 200
    assert r.json() == {
        "active_total": 0,
        "closing_today": 0,
        "closing_7d": 0,
        "needs_analysis": 0,
        "needs_grade": 0,
        "ready_for_submission": 0,
        "blocked_documents": 0,
    }


def test_notice_summary_counts_work_queue_buckets(client, sqlite_engine):
    now = datetime.now(tz=UTC)
    _seed_notice(
        sqlite_engine,
        notice_no="COLLECTED-000",
        status="collected",
        close_date=now + timedelta(hours=2),
    )
    _seed_notice(
        sqlite_engine,
        notice_no="ANALYZED-000",
        status="analyzed",
        close_date=now + timedelta(days=3),
    )
    _seed_notice(
        sqlite_engine,
        notice_no="GRADED-000",
        status="analyzed",
        close_date=now + timedelta(days=9),
        graded_at=now,
    )
    _seed_notice(
        sqlite_engine,
        notice_no="DOCS-000",
        status="form_filled",
        close_date=now + timedelta(days=4),
        analysis={
            "document_automation": {
                "ready_for_submission": True,
                "checklist": [
                    {"id": "bid_form", "status": "generated"},
                    {"id": "price", "status": "blocked"},
                ],
            }
        },
    )
    _seed_notice(
        sqlite_engine,
        notice_no="CLOSED-000",
        status="collected",
        close_date=now - timedelta(days=1),
    )

    r = client.get("/notices/summary")

    assert r.status_code == 200
    body = r.json()
    assert body["active_total"] == 4
    assert body["closing_today"] == 1
    assert body["closing_7d"] == 3
    assert body["needs_analysis"] == 2
    assert body["needs_grade"] == 1
    assert body["ready_for_submission"] == 1
    assert body["blocked_documents"] == 1


def test_notice_summary_requires_api_key(sqlite_engine, monkeypatch):
    from api.config import settings
    from api.main import app

    monkeypatch.setattr(settings, "api_key", "secret-test-key")
    client = TestClient(app)

    r = client.get("/notices/summary")

    assert r.status_code in (401, 403)
