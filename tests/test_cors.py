"""CORS 미들웨어 통합 테스트 (M7).

Next.js 프론트(:3000)가 API(:8001)를 호출할 때 브라우저 차단되지 않도록
preflight OPTIONS + Access-Control-Allow-Origin 응답을 검증.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import settings
from api.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    return TestClient(app)


def test_cors_preflight_allows_localhost_3000(client):
    r = client.options(
        "/notices",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_simple_get_returns_allow_origin_header(client):
    """단순 GET 요청에도 ACAO 헤더가 응답에 포함된다 (브라우저가 검사)."""
    r = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_blocks_unknown_origin(client):
    """frontend_origin에 없는 origin은 ACAO 헤더 미반환 (브라우저 차단)."""
    r = client.get("/healthz", headers={"Origin": "https://evil.example.com"})
    # 응답 자체는 200 (CORS는 응답 헤더로만 표현)
    assert r.status_code == 200
    # FastAPI/Starlette는 허용 외 origin에 대해 ACAO 헤더를 생략
    assert "access-control-allow-origin" not in {k.lower(): v for k, v in r.headers.items()}
