from __future__ import annotations

from fastapi.testclient import TestClient

from api.config import settings
from api.main import app


def test_hwp_agent_health_ok(monkeypatch):
    class HealthyClient:
        base_url = "http://hwp-agent.test"

        def health(self):
            return True

    monkeypatch.setattr("api.routers.documents.HwpAgentClient", lambda: HealthyClient())
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "scheduler_enabled", False)

    response = TestClient(app).get("/documents/hwp-agent/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "base_url": "http://hwp-agent.test",
        "detail": None,
    }


def test_hwp_agent_health_unavailable(monkeypatch):
    class UnhealthyClient:
        base_url = "http://hwp-agent.test"

        def health(self):
            return False

    monkeypatch.setattr("api.routers.documents.HwpAgentClient", lambda: UnhealthyClient())
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "scheduler_enabled", False)

    response = TestClient(app).get("/documents/hwp-agent/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["base_url"] == "http://hwp-agent.test"
    assert "not reachable" in body["detail"]
