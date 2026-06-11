"""/healthz DB 핑 테스트.

DB 미설정·연결 실패 시에도 200 OK + checks.db에 사유 문자열.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from api.config import settings
from api.main import app
from api.routers.notices import metadata


@pytest.fixture
def client_with_sqlite(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    monkeypatch.setattr("api.main.get_engine", lambda: engine)
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


@pytest.fixture
def client_no_db(monkeypatch):
    from api.db import MissingDatabaseUrl

    def boom():
        raise MissingDatabaseUrl("DATABASE_URL is not set")

    monkeypatch.setattr("api.main.get_engine", boom)
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


def test_healthz_returns_ok_with_db_check(client_with_sqlite):
    r = client_with_sqlite.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["checks"]["db"] == "ok"


def test_healthz_reports_db_missing_when_url_unset(client_no_db):
    r = client_no_db.get("/healthz")
    assert r.status_code == 200  # 항상 200 (Docker HEALTHCHECK용)
    body = r.json()
    assert body["ok"] is False
    assert "DATABASE_URL not set" in body["checks"]["db"]


def test_healthz_reports_db_error_on_connection_failure(monkeypatch):
    """get_engine() 자체는 성공하나 .connect()가 raise할 때 error: 메시지."""
    from unittest.mock import MagicMock

    bad_engine = MagicMock()
    bad_engine.connect.side_effect = RuntimeError("connection refused")

    monkeypatch.setattr("api.main.get_engine", lambda: bad_engine)
    monkeypatch.setattr(settings, "scheduler_enabled", False)

    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["checks"]["db"].startswith("error:")
    assert "connection refused" in body["checks"]["db"]
