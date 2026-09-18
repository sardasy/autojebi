"""Isolated v2 credential/role tests; all credentials below are fictitious fixtures."""

import hashlib
import json

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient

from api.auth import verify_api_key
from api.config import settings
from api.workspace.identity import audit_details
from api.workspace.identity import router as identity_router

TOKENS = {role: f"fixture-{role}-" + "x" * 40 for role in ("viewer", "writer", "reviewer", "approver")}


def users():
    return [{"id": role, "name": f"Test {role}", "role": role,
             "token_sha256": hashlib.sha256(token.encode()).hexdigest()}
            for role, token in TOKENS.items()]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "fixture-shared-key")
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", json.dumps(users()))
    monkeypatch.setenv("WORKSPACE_AUTH_REGISTRY", "")
    app = FastAPI()
    router = APIRouter(prefix="/v2", dependencies=[Depends(verify_api_key)])
    router.include_router(identity_router)

    async def mutation(request: Request):
        body = await request.json()
        return audit_details(body)

    for path in ["/notices/N/reviews", "/notices/N/sections/S/review",
                 "/notices/N/documents/D/review", "/notices/sections/documents/D/review", "/notices/N/form-fillings/F/review",
                 "/notices/N/requirements", "/notices/N/source-review", "/notices/N/documents",
                 "/notices/N/decision", "/notices/N/output-plan", "/company-assets/A", "/search"]:
        router.add_api_route(path, mutation, methods=["POST", "PUT"])
    app.include_router(router)

    @app.get("/legacy", dependencies=[Depends(verify_api_key)])
    def legacy():
        return audit_details()

    with TestClient(app) as instance:
        yield instance


def headers(role):
    return {"X-API-Key": "fixture-shared-key", "Authorization": f"Bearer {TOKENS[role]}"}


def test_all_v2_reads_require_personal_credentials_even_with_shared_key(client):
    assert client.get("/v2/identity", headers={"X-API-Key": "fixture-shared-key"}).status_code == 401
    assert client.get("/v2/identity", headers={"Authorization": f"Bearer {TOKENS['viewer']}"}).status_code == 403
    response = client.get("/v2/identity", headers=headers("viewer"))
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "actor": {"id": "viewer", "name": "Test viewer", "role": "viewer"}}
    assert "token" not in response.text


def test_disabled_mode_and_legacy_remain_compatible(client, monkeypatch):
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "false")
    assert client.get("/v2/identity", headers={"X-API-Key": "fixture-shared-key"}).json() == {"enabled": False, "actor": None}
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "true")
    assert client.get("/legacy", headers={"X-API-Key": "fixture-shared-key"}).json() == {}


@pytest.mark.parametrize(("path", "body", "allowed"), [
    ("/notices/N/reviews", {"action": "ready"}, "approver"),
    ("/notices/N/reviews", {"action": "approved"}, "reviewer"),
    ("/notices/N/reviews", {"action": "rejected"}, "reviewer"),
    ("/notices/N/sections/S/review", {"approved": True}, "reviewer"),
    ("/notices/N/sections/S/review", {"approved": False}, "reviewer"),
    ("/notices/N/sections/S/review", {"approved": "true"}, "reviewer"),
    ("/notices/N/sections/S/review", {"approved": None}, "writer"),
    ("/notices/N/documents/D/review", {"confirmed": True}, "reviewer"),
    ("/notices/sections/documents/D/review", {"confirmed": True}, "reviewer"),
    ("/notices/N/form-fillings/F/review", {"approved": True}, "reviewer"),
    ("/notices/N/form-fillings/F/review", {"approved": False}, "reviewer"),
    ("/notices/N/requirements", {"review_status": "accepted"}, "reviewer"),
    ("/notices/N/requirements", {"compliance": "meets"}, "reviewer"),
    ("/notices/N/requirements", {"review_status": "pending", "compliance": "unassessed"}, "writer"),
    ("/notices/N/source-review", {}, "reviewer"),
    ("/notices/N/documents", {}, "writer"),
    ("/notices/N/decision", {}, "writer"),
    ("/notices/N/output-plan", {}, "writer"),
    ("/company-assets/A", {}, "writer"),
])
def test_roles_cannot_write_review_or_approve_for_each_other(client, path, body, allowed):
    for role in TOKENS:
        response = client.post(f"/v2{path}", headers=headers(role), json=body)
        assert response.status_code == (200 if role == allowed else 403), (path, role, response.text)
        if role == allowed:
            assert response.json()["actor"]["role"] == role


def test_read_only_search_is_available_to_viewer(client):
    assert client.post("/v2/search", headers=headers("viewer"), json={}).status_code == 200


def test_user_headers_body_and_cookies_cannot_impersonate_roles(client):
    forged = {**headers("writer"), "X-Actor-Id": "approver", "X-Workspace-Role": "approver", "X-User-Role": "approver"}
    assert client.post("/v2/notices/N/reviews", headers=forged, json={"action": "ready", "actor": {"role": "approver"}}).status_code == 403
    response = client.post("/v2/notices/N/documents", headers=forged, json={"actor": {"id": "other", "role": "approver"}})
    assert response.json()["actor"] == {"id": "writer", "name": "Test writer", "role": "writer"}
    assert client.get("/v2/identity", headers={"X-API-Key": "fixture-shared-key", "Cookie": f"autojebi_workspace_session={TOKENS['approver']}"}).status_code == 401
    assert audit_details({"actor": {"id": "forged"}}) == {}


def test_registry_revocation_and_role_change_apply_without_restart(client, monkeypatch):
    records = users()
    records[1]["role"] = "viewer"
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", json.dumps(records))
    assert client.post("/v2/notices/N/documents", headers=headers("writer"), json={}).status_code == 403
    records[1]["enabled"] = False
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", json.dumps(records))
    assert client.get("/v2/identity", headers=headers("writer")).status_code == 401


@pytest.mark.parametrize("raw", ["", "not-json", "[]", "{}", '[{"token_sha256":"secret-marker"}]'])
def test_bad_or_empty_registry_fails_closed_without_exposing_inputs(client, monkeypatch, raw):
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", raw)
    response = client.get("/v2/identity", headers=headers("writer"))
    assert response.status_code == 503
    assert "secret-marker" not in response.text
    assert TOKENS["writer"] not in response.text


def test_local_registry_and_duplicate_ids_or_hashes(client, monkeypatch, tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(users()), encoding="utf-8")
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", "")
    monkeypatch.setenv("WORKSPACE_AUTH_REGISTRY", str(path))
    assert client.get("/v2/identity", headers=headers("writer")).status_code == 200
    records = users()
    records[1]["token_sha256"] = records[0]["token_sha256"]
    path.write_text(json.dumps(records), encoding="utf-8")
    assert client.get("/v2/identity", headers=headers("writer")).status_code == 503
