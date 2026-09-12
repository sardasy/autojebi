import hashlib

import httpx
import pytest

from api.services.hwp_agent_client import HwpAgentClient
from api.workspace import prerequisites as checks


@pytest.mark.parametrize(
    "status,body,code",
    [
        (
            200,
            {"ok": False, "recovery_required": True, "secret": "never-return"},
            "worker_recovery",
        ),
        (401, {"detail": "never-return"}, "worker_auth"),
        (200, [], "worker_invalid_health"),
        (200, {"ok": "true"}, "worker_unhealthy"),
        (200, {"ok": True, "generation_verified": False}, "worker_connected"),
        (503, {"detail": "never-return"}, "worker_offline"),
    ],
)
def test_worker_diagnostics_sanitized(status, body, code):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(status, json=body)

    client = HwpAgentClient(token="x" * 32, transport=httpx.MockTransport(handler))
    value = client.diagnostics()
    assert value["code"] == code
    assert "never-return" not in str(value)
    assert calls == [("GET", "/health")]
    assert not value["generation_verified"]


def test_worker_missing_token_never_contacts_provider(monkeypatch):
    monkeypatch.delenv("HWP_AGENT_TOKEN", raising=False)
    client = HwpAgentClient(
        token="short", transport=httpx.MockTransport(lambda r: pytest.fail("network"))
    )
    assert client.diagnostics()["code"] == "worker_token_missing"


@pytest.fixture
def preflight(monkeypatch, tmp_path):
    monkeypatch.setenv("HWP_TEMPLATE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        checks,
        "hwp_preview",
        lambda *_: {
            "template": {"template_path": "missing.hwp"},
            "values": {"company_name": "Registered"},
            "required_missing": [],
        },
    )
    monkeypatch.setattr(
        HwpAgentClient,
        "diagnostics",
        lambda *_: {
            "available": False,
            "code": "worker_recovery",
            "recovery_required": True,
        },
    )
    return {
        "documents": [
            {"id": "s", "role": "notice_source", "text": "Need registration", "confirmed": True},
            {"id": "r", "role": "company_reference", "text": "Registered", "confirmed": True},
        ],
        "requirements": [
            {
                "id": "q",
                "text": "Information registration 0036",
                "category": "qualification",
                "document_id": "s",
                "quote": "Need registration",
                "locator": "page 1",
                "review_status": "accepted",
                "compliance": "meets",
                "evidence_id": "r",
                "evidence_quote": "Registered",
                "evidence_locator": "page 1",
                "proposed_value": "Yes",
            }
        ],
        "source_reviewed": False,
    }


def test_values_present_does_not_imply_template_worker_or_qualification_ready(preflight):
    value = checks.check_prerequisites(None, preflight, 5, "proposal")
    rows = {i.code: i for i in value.items}
    assert value.input_version == 5 and value.required_missing == []
    assert not value.hwp_request_available
    assert rows["hwp_template"].blocks_hwp and rows["worker_recovery"].blocks_hwp
    assert rows["qualification_q"].state == "blocked"
    assert rows["company_evidence"].state == "blocked"
    assert rows["references"].state == "checked"
    assert preflight["source_reviewed"] is False


def test_valid_hwp_draft_conditions_do_not_approve_business_requirements(
    preflight, tmp_path, monkeypatch
):
    monkeypatch.setattr(checks, "validate_hwp_content", lambda *_: {})
    (tmp_path / "missing.hwp").write_bytes(b"test-document")
    monkeypatch.setattr(
        HwpAgentClient,
        "diagnostics",
        lambda *_: {
            "available": True,
            "code": "worker_connected",
            "recovery_required": False,
        },
    )
    value = checks.check_prerequisites(None, preflight, 5, "proposal")
    assert not value.hwp_request_available
    preview = checks.hwp_preview(None, preflight, "proposal")
    inspection = {"template_sha256": hashlib.sha256(b"test-document").hexdigest(),
                  "mapping_sha256": checks.mapping_hash(preview["template"], []), "inspection_passed": True}
    value = checks.check_prerequisites(None, preflight, 5, "proposal", inspection=inspection)
    assert value.hwp_request_available
    assert next(i for i in value.items if i.code == "qualification_q").state == "blocked"
    assert next(i for i in value.items if i.code == "hwp_readback").state == "review"


@pytest.mark.parametrize("path", ["../outside.hwp", "fake.hwp"])
def test_invalid_or_outside_template_blocked(preflight, monkeypatch, tmp_path, path):
    (tmp_path / "fake.hwp").write_bytes(b"not a document")
    monkeypatch.setattr(
        checks,
        "hwp_preview",
        lambda *_: {
            "template": {"template_path": path},
            "values": {},
            "required_missing": [],
        },
    )
    value = checks.check_prerequisites(None, preflight, 5, "proposal")
    assert next(i for i in value.items if i.code == "hwp_template").blocks_hwp


def test_route_is_read_only_and_exposes_version(client, preflight, monkeypatch):
    from api.routers import workspace

    monkeypatch.setattr(
        workspace.service,
        "load",
        lambda *_: {"inputs": preflight, "version": 7, "source_hash": "old"},
    )
    monkeypatch.setattr(workspace.service, "source_data", lambda *_: ({}, "changed"))
    response = client.get("/v2/notices/check/prerequisites?template_key=proposal")
    assert response.status_code == 200
    value = response.json()
    assert value["input_version"] == 7 and value["template_key"] == "proposal"
    assert value["mapping_fields"] == ["company_name"] and value["checked_at"]
    assert not value["hwp_request_available"]
    assert next(i for i in value["items"] if i["code"] == "source_changed")["blocks_hwp"]
