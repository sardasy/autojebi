"""WorkspaceError must produce exactly the response HTTPException produced before R2 (ADR 0001)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers.workspace import install_error_handlers
from api.workspace import service
from api.workspace.errors import HANDLED_ERRORS, WorkspaceError


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/domain")
    def domain():
        service.fail("version_conflict", "입력이 변경되었습니다.", status=409)

    @app.get("/legacy")
    def legacy():
        raise HTTPException(
            status_code=409,
            detail={"code": "version_conflict", "message": "입력이 변경되었습니다.",
                    "next_action": "입력과 최신 상태를 확인하세요.", "job_id": None},
        )

    return app


def test_domain_error_response_matches_http_exception():
    client = TestClient(_app())
    domain, legacy = client.get("/domain"), client.get("/legacy")
    assert domain.status_code == legacy.status_code == 409
    assert domain.json() == legacy.json()
    assert domain.json()["detail"]["code"] == "version_conflict"


def test_handled_errors_cover_domain_and_legacy():
    assert issubclass(WorkspaceError, HANDLED_ERRORS)
    assert issubclass(HTTPException, HANDLED_ERRORS)
    assert str(WorkspaceError(502, "x")) == str(HTTPException(502, "x"))
