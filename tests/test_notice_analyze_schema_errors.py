from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.main import app
from api.routers import notices
from api.routers.notices import bid_pipeline, metadata, notice_errors
from api.services.claude_analyzer import AnalyzeResult


@pytest.fixture
def sqlite_engine(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    monkeypatch.setattr("api.db.get_engine", lambda: engine)
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return engine


@pytest.fixture
def client(sqlite_engine):
    return TestClient(app)


def test_analyze_records_claude_schema_errors(client, sqlite_engine, monkeypatch):
    now = datetime.now(tz=UTC)
    with sqlite_engine.begin() as conn:
        conn.execute(
            insert(bid_pipeline).values(
                notice_no="ANALYZE-SCHEMA-1",
                title="변압기 구매",
                source="G2B",
                raw={},
                category="비관련",
                fit_score=0,
                assignee="미배정",
                analysis={},
                status="collected",
                created_at=now,
                updated_at=now,
            )
        )

    class FakeAnalyzer:
        def analyze_notice(self, **_kwargs):
            return AnalyzeResult(
                category="비관련",
                fit_score=0,
                analysis={
                    "source": "claude_schema_v1",
                    "elec_spec": {},
                    "schema_valid": False,
                    "schema_errors": ["Input should be a valid number"],
                },
            )

    monkeypatch.setattr(notices, "ClaudeAnalyzer", lambda: FakeAnalyzer())

    response = client.post("/notices/ANALYZE-SCHEMA-1/analyze")

    assert response.status_code == 200, response.text
    assert response.json()["analysis"]["schema_valid"] is False
    with sqlite_engine.begin() as conn:
        error = conn.execute(
            select(notice_errors).where(notice_errors.c.notice_no == "ANALYZE-SCHEMA-1")
        ).mappings().one()
    assert error["stage"] == "claude.schema"
    assert error["source"] == "claude"
    assert error["detail"] == "Input should be a valid number"
