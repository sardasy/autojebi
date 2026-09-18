"""Real workspace response/audit integration using an isolated database and fake account."""

import hashlib
import json

from sqlalchemy import select

from api.workspace import service
from api.workspace.tables import reviews


def test_workspace_review_response_exposes_authenticated_actor_and_retains_legacy_null(
    client, sqlite_engine, monkeypatch,
):
    token = "fixture-integration-writer-" + "x" * 40
    actor = {"id": "integration-writer", "name": "Integration Writer", "role": "writer"}
    monkeypatch.setenv("WORKSPACE_AUTH_ENABLED", "true")
    monkeypatch.setenv("WORKSPACE_AUTH_USERS", json.dumps([
        {**actor, "token_sha256": hashlib.sha256(token.encode()).hexdigest()},
    ]))
    monkeypatch.setenv("WORKSPACE_AUTH_REGISTRY", "")
    headers = {"Authorization": f"Bearer {token}"}
    identity = client.get("/v2/identity", headers=headers)
    assert identity.status_code == 200
    assert identity.json() == {"enabled": True, "actor": actor}
    response = client.post("/v2/notices", headers=headers, json={
        "notice_no": "E2E-IDENTITY", "title": "Identity fixture", "source": "MANUAL_E2E", "raw": {},
    })
    assert response.status_code == 200, response.text
    response = client.post("/v2/notices/E2E-IDENTITY/initialize", headers=headers)
    assert response.status_code == 200, response.text
    response = client.post("/v2/notices/E2E-IDENTITY/decision", headers=headers, json={
        "version": response.json()["version"], "decision": "hold", "note": "Identity integration test",
    })
    assert response.status_code == 200, response.text
    recorded = next(item for item in response.json()["reviews"] if item["action"] == "decision")
    assert "actor" in recorded
    assert recorded["actor"] == actor
    with sqlite_engine.begin() as conn:
        stored = conn.execute(select(reviews.c.details).where(reviews.c.id == recorded["id"])).scalar_one()
        assert stored["actor"] == actor
        ws = service.load(conn, "E2E-IDENTITY")
        service.audit(conn, ws, "legacy_fixture", "Record without personal context", {})
    fetched = client.get("/v2/notices/E2E-IDENTITY/workspace", headers=headers)
    assert fetched.status_code == 200
    legacy = next(item for item in fetched.json()["reviews"] if item["action"] == "legacy_fixture")
    assert "actor" in legacy and legacy["actor"] is None
    assert token not in fetched.text and "token_sha256" not in fetched.text
