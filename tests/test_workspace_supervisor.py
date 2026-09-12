import json
from types import SimpleNamespace
from unittest.mock import Mock

from api.workspace.supervisor import supervise


def test_supervisor_restarts_exited_worker_and_records_pid(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_DATA_DIR", str(tmp_path))
    count = 0
    stop = Mock()
    stop.is_set.side_effect = lambda: count >= 3
    child = SimpleNamespace(pid=123, returncode=1, poll=lambda: 1)

    def spawn(command, **kwargs):
        nonlocal count
        count += 1
        assert command[-2:] == ["-m", "api.workspace.worker"]
        assert "creationflags" in kwargs
        return child

    supervise(stop, spawn)
    assert count == 3
    assert stop.wait.call_count == 2
    value = json.loads((tmp_path / "worker-supervisor.json").read_text())
    assert value["state"] == "stopped" and value["worker_pid"] == 123


def test_worker_health_rejects_stale_heartbeat(client, monkeypatch):
    monkeypatch.setattr(
        "api.workspace.receipts.read_health",
        lambda lane="all": {
            "state": "idle",
            "heartbeat_at": "2000-01-01T00:00:00+00:00",
            "last_failure": None,
        },
    )
    response = client.get("/v2/worker/health")
    assert response.status_code == 200
    assert response.json()["available"] is False
