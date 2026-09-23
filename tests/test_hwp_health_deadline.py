import asyncio
import json

import httpx
import pytest

from api.services.hwp_health import diagnostics


def test_diagnostic_deadline_covers_hanging_response_and_has_no_retries(monkeypatch):
    monkeypatch.setenv("HWP_AGENT_TOKEN", "test-only-" + "x" * 32)
    calls = []

    async def handle(request):
        calls.append(request)
        await asyncio.sleep(60)

    async def run():
        async with asyncio.timeout(1):
            return await diagnostics(transport=httpx.MockTransport(handle), deadline=0.01)

    assert asyncio.run(run())["code"] == "worker_timeout"
    assert len(calls) == 1


@pytest.mark.parametrize(("body", "code"), [
    ({"ok": True}, "worker_connected"),
    ({"ok": False, "state": "running"}, "worker_running"),
    ({"ok": False, "recovery_required": True}, "worker_recovery"),
    ({"ok": "yes"}, "worker_invalid_health"),
    ({"ok": False}, "worker_unhealthy"),
])
def test_health_states_and_safe_diagnostics(monkeypatch, body, code):
    monkeypatch.setenv("HWP_AGENT_TOKEN", "test-only-" + "x" * 32)
    payload = {**body, "secret": "DO_NOT_EXPOSE", "operation": {"stage": "save", "path": "PRIVATE"}}
    result = asyncio.run(diagnostics(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))))
    assert result["code"] == code
    assert result["generation_verified"] is False
    assert "DO_NOT_EXPOSE" not in json.dumps(result) and "PRIVATE" not in json.dumps(result)
