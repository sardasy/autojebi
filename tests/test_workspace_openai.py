import json

import httpx
import pytest

from api.config import settings
from api.workspace import openai_client, providers
from api.workspace.errors import WorkspaceError
from api.workspace.proposal import Draft


@pytest.fixture
def openai_settings(monkeypatch):
    monkeypatch.setattr(settings, "workspace_llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "test-private-key")
    monkeypatch.setattr(settings, "openai_model", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "openai_max_output_tokens", 16384)


def request():
    return providers.prepare_request({
        "model": "claude-test", "max_tokens": 6000, "system": "Grounded only",
        "messages": [{"role": "user", "content": "Public test source"}],
        "tools": [{"name": "proposal", "input_schema": Draft.model_json_schema()}],
    })


def wire_result(value=None):
    return {"status": "completed", "error": None, "output": [
        {"type": "reasoning", "summary": [{"text": "not the result"}]},
        {"type": "message", "role": "assistant", "status": "completed", "content": [
            {"type": "output_text", "text": json.dumps(value if value is not None else {"ok": True})},
        ]},
    ]}


def mock_http(monkeypatch, handler):
    client_class = httpx.Client

    def client(**kwargs):
        assert kwargs == {"timeout": 180, "follow_redirects": False}
        return client_class(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(openai_client.httpx, "Client", client)


def test_responses_payload_and_strict_schema(openai_settings, monkeypatch):
    calls = []

    def handler(req):
        calls.append(req)
        assert str(req.url) == "https://api.openai.com/v1/responses"
        assert req.headers["Authorization"] == "Bearer test-private-key"
        assert "test-private-key" not in req.content.decode()
        body = json.loads(req.content)
        assert body["model"] == "gpt-4.1-mini"
        assert body["store"] is False
        assert body["max_output_tokens"] == 16384
        assert body["instructions"] == "Grounded only"
        assert body["input"][0]["content"] == "Public test source"
        fmt = body["text"]["format"]
        assert fmt["type"] == "json_schema" and fmt["strict"] is True
        assert fmt["name"] == "proposal"
        assert fmt["schema"]["additionalProperties"] is False
        assert fmt["schema"]["$defs"]["Section"]["additionalProperties"] is False
        assert set(fmt["schema"]["$defs"]["Section"]["required"]) == {"text", "requirement_ids", "evidence_ids"}
        return httpx.Response(200, json=wire_result())

    mock_http(monkeypatch, handler)
    assert providers.generate(request()) == {"ok": True}
    assert len(calls) == 1


@pytest.mark.parametrize(("status", "body", "code"), [
    (401, {}, "llm_authentication_failed"),
    (403, {}, "llm_authentication_failed"),
    (429, {}, "llm_rate_limited"),
    (404, {}, "llm_model_unavailable"),
    (400, {}, "llm_provider_error"),
    (500, {}, "llm_provider_error"),
    (302, {}, "llm_provider_error"),
    (200, {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}, "llm_output_limit"),
    (200, {"status": "incomplete", "incomplete_details": {"reason": "content_filter"}}, "llm_incomplete_response"),
    (200, {"status": "failed", "error": {"message": "private error"}}, "llm_provider_error"),
    (200, {"status": "queued"}, "llm_provider_error"),
    (200, {"status": "completed", "output": []}, "invalid_llm_response"),
    (200, wire_result(["not an object"]), "invalid_llm_response"),
    (200, {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "incomplete", "content": []}]}, "llm_incomplete_response"),
    (200, {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "private reason"}]}]}, "llm_response_blocked"),
    (200, {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "broken"}]}]}, "invalid_llm_response"),
])
def test_safe_errors_no_retries(openai_settings, monkeypatch, status, body, code):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={**body, "private": "test-private-key"})

    mock_http(monkeypatch, handler)
    with pytest.raises(WorkspaceError) as error:
        openai_client.generate(request())
    assert error.value.detail["code"] == code
    assert error.value.status_code >= 500
    assert "private" not in str(error.value.detail)
    assert len(calls) == 1
    if status != 200 and code == "llm_provider_error":
        assert f"HTTP {status}" in error.value.detail["message"]


@pytest.mark.parametrize(("exception", "code"), [
    (httpx.ReadTimeout, "llm_timeout"), (httpx.ConnectError, "llm_connection_failed"),
])
def test_transport_errors(openai_settings, monkeypatch, exception, code):
    def handler(req):
        raise exception("private details", request=req)

    mock_http(monkeypatch, handler)
    with pytest.raises(WorkspaceError) as error:
        openai_client.generate(request())
    assert error.value.detail["code"] == code
    assert "private details" not in str(error.value.detail)


def test_missing_key_and_invalid_model(openai_settings, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert providers.configured_key() == ""
    with pytest.raises(WorkspaceError, match="llm_not_configured"):
        openai_client.generate({})
    monkeypatch.setattr(settings, "openai_model", "https://other-host/key")
    with pytest.raises(WorkspaceError, match="llm_model_invalid"):
        request()


def test_schema_is_copied_and_rejects_implicit_optional_fields():
    original = Draft.model_json_schema()
    converted = openai_client.strict_schema(original)
    assert "additionalProperties" not in original
    assert converted["additionalProperties"] is False
    with pytest.raises(WorkspaceError, match="llm_schema_invalid"):
        openai_client.strict_schema({"type": "object", "properties": {"value": {"type": "string"}}})


def test_settings_exposes_openai_without_secret(client, openai_settings):
    response = client.get("/v2/settings")
    assert response.status_code == 200
    assert response.json()["configured"]["llm"] is True
    assert response.json()["llm"] == {
        "provider": "openai", "model": "gpt-4.1-mini",
        "key_registered": True, "connection_status": "not_checked",
    }
    assert "test-private-key" not in response.text
