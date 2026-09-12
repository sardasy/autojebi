import json

import httpx
import pytest
from fastapi import HTTPException

from api.config import settings
from api.workspace import gemini, providers


@pytest.fixture
def gemini_settings(monkeypatch):
    monkeypatch.setattr(settings, "workspace_llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-private-key")
    monkeypatch.setattr(settings, "gemini_model", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "gemini_max_output_tokens", 16384)


def request():
    return gemini.prepare_request({
        "model": "claude-test", "max_tokens": 6000, "system": "Grounded only",
        "messages": [{"role": "user", "content": "Public test source"}],
        "tools": [{"input_schema": {"type": "object", "properties": {}}}],
    })


def wire_result(value=None, finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [
        {"text": "not the result", "thought": True},
        {"text": json.dumps(value if value is not None else {"requirements": []})},
    ]}}]}


def mock_http(monkeypatch, handler):
    client_class = httpx.Client

    def client(**kwargs):
        assert kwargs == {"timeout": 180, "follow_redirects": False}
        return client_class(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(gemini.httpx, "Client", client)


def test_payload_key_header_and_no_thought_content(gemini_settings, monkeypatch):
    calls = []

    def handler(req):
        calls.append(req)
        assert str(req.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        assert req.headers["x-goog-api-key"] == "test-private-key"
        assert "test-private-key" not in req.content.decode()
        body = json.loads(req.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseJsonSchema"]["type"] == "object"
        assert body["generationConfig"]["maxOutputTokens"] == 16384
        assert body["systemInstruction"]["parts"][0]["text"] == "Grounded only"
        assert body["contents"][0]["parts"][0]["text"] == "Public test source"
        return httpx.Response(200, json=wire_result({"ok": True}))

    mock_http(monkeypatch, handler)
    assert gemini.generate(request()) == {"ok": True}
    assert len(calls) == 1


@pytest.mark.parametrize(("status", "body", "code"), [
    (401, {}, "llm_authentication_failed"),
    (403, {}, "llm_authentication_failed"),
    (400, {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}, "llm_authentication_failed"),
    (429, {}, "llm_rate_limited"),
    (404, {}, "llm_model_unavailable"),
    (500, {}, "llm_provider_error"),
    (302, {}, "llm_provider_error"),
    (400, {}, "llm_provider_error"),
    (200, {"promptFeedback": {"blockReason": "SAFETY"}}, "llm_response_blocked"),
    (200, wire_result(finish="MAX_TOKENS"), "llm_output_limit"),
    (200, wire_result(finish="SAFETY"), "llm_response_blocked"),
    (200, wire_result(finish="RECITATION"), "llm_response_blocked"),
    (200, wire_result(finish="UNKNOWN_PRIVATE_VALUE"), "llm_incomplete_response"),
    (200, {"candidates": []}, "llm_incomplete_response"),
    (200, wire_result(["not an object"]), "invalid_llm_response"),
    (200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "broken"}]}}]}, "invalid_llm_response"),
    (200, {"candidates": None}, "invalid_llm_response"),
])
def test_safe_errors_without_retries(gemini_settings, monkeypatch, status, body, code):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={**body, "private": "test-private-key"})

    mock_http(monkeypatch, handler)
    with pytest.raises(HTTPException) as error:
        gemini.generate(request())
    assert error.value.detail["code"] == code
    if code == "llm_provider_error":
        assert f"HTTP {status}" in error.value.detail["message"]
    assert error.value.status_code >= 500
    assert "test-private-key" not in str(error.value.detail)
    assert len(calls) == 1


@pytest.mark.parametrize(("exception", "code"), [
    (httpx.ReadTimeout, "llm_timeout"), (httpx.ConnectError, "llm_connection_failed"),
])
def test_transport_errors(gemini_settings, monkeypatch, exception, code):
    def handler(req):
        raise exception("private details", request=req)

    mock_http(monkeypatch, handler)
    with pytest.raises(HTTPException) as error:
        gemini.generate(request())
    assert error.value.detail["code"] == code
    assert "private details" not in str(error.value.detail)


def test_invalid_model_and_no_key_do_not_send(gemini_settings, monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "../../other-host?key=secret")
    with pytest.raises(HTTPException, match="llm_model_invalid"):
        request()
    monkeypatch.setattr(settings, "google_api_key", "")
    assert providers.configured_key() == ""
    with pytest.raises(HTTPException, match="llm_not_configured"):
        gemini.generate({})


def test_settings_exposes_provider_without_key(client, gemini_settings):
    response = client.get("/v2/settings")
    assert response.status_code == 200
    assert response.json()["configured"]["llm"] is True
    assert response.json()["llm"] == {
        "provider": "gemini", "model": "gemini-2.5-flash",
        "key_registered": True, "connection_status": "not_checked",
    }
    assert "test-private-key" not in response.text
