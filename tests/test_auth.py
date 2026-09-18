"""X-API-Key 인증 테스트 (M9).

- API_KEY 빈값 → 인증 자동 비활성 (기존 테스트 무회귀 보장)
- /healthz는 인증 무관 (Docker HEALTHCHECK 호환)
- API_KEY 설정 시 라우터에 키 없으면 403
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app


@pytest.fixture
def client_no_auth(monkeypatch):
    """API_KEY 빈값 — 인증 비활성."""
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


@pytest.fixture
def client_with_auth(monkeypatch):
    """API_KEY=secret123 — 인증 활성."""
    monkeypatch.setattr(settings, "api_key", "secret123")
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


def test_healthz_never_requires_auth(client_with_auth):
    """API_KEY 설정되어 있어도 /healthz는 통과 (Docker HEALTHCHECK용)."""
    r = client_with_auth.get("/healthz")
    assert r.status_code == 200


def test_auth_disabled_when_api_key_blank(client_no_auth):
    """빈 키 → 헤더 없이 라우터 호출 가능 (기존 테스트 무회귀)."""
    r = client_no_auth.get("/notices")
    # DB 없으면 500이지만 인증 자체는 통과 — 403이 아님이 핵심
    assert r.status_code != 403


def test_get_notices_403_without_key(client_with_auth):
    r = client_with_auth.get("/notices")
    assert r.status_code == 403
    assert "X-API-Key" in r.json().get("detail", "")


def test_get_notices_403_with_wrong_key(client_with_auth):
    r = client_with_auth.get("/notices", headers={"X-API-Key": "wrong"})
    assert r.status_code == 403


def test_get_notices_passes_with_correct_key(client_with_auth):
    """올바른 키 → 인증 통과 (DB 없으면 500은 무관, 403이 아니면 OK)."""
    r = client_with_auth.get("/notices", headers={"X-API-Key": "secret123"})
    assert r.status_code != 403


def test_post_upsert_requires_key(client_with_auth):
    r = client_with_auth.post(
        "/notices/upsert", json={"notice_no": "T-X"}
    )
    assert r.status_code == 403


def test_skus_ingest_requires_key(client_with_auth):
    r = client_with_auth.post("/skus/ingest", json={})
    assert r.status_code == 403


def test_production_refuses_to_start_without_api_key(monkeypatch):
    """APP_ENV=production + API_KEY 공란 → 기동 거부 (인증 우회 모드가 운영에 나가지 않게)."""
    from api.main import enforce_auth_policy

    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(RuntimeError, match="API_KEY"):
        enforce_auth_policy()


def test_production_starts_with_api_key(monkeypatch):
    from api.main import enforce_auth_policy

    monkeypatch.setattr(settings, "api_key", "x" * 32)
    monkeypatch.setattr(settings, "app_env", "production")
    enforce_auth_policy()


def test_development_only_warns_without_api_key(monkeypatch, caplog):
    from api.main import enforce_auth_policy

    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "app_env", "development")
    with caplog.at_level("WARNING", logger="api.main"):
        enforce_auth_policy()
    assert any("API_KEY" in r.getMessage() for r in caplog.records)
