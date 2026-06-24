from __future__ import annotations

import json

import httpx
import pytest

from api.services.hwp_agent_client import (
    AutofillOutcome,
    HwpAgentClient,
    HwpAgentError,
    PutFieldsOutcome,
)


def _make_client(handler, *, token: str | None = None) -> HwpAgentClient:
    transport = httpx.MockTransport(handler)
    return HwpAgentClient(
        base_url="http://hwp-agent.test",
        token=token,
        timeout_s=2.0,
        connect_timeout_s=2.0,
        retries=2,
        transport=transport,
    )


def test_health_returns_true_on_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"ok": True, "service": "milim-hwp-agent"})

    client = _make_client(handler)
    assert client.health() is True


def test_health_returns_false_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"ok": False})

    client = _make_client(handler)
    assert client.health() is False


def test_autofill_sends_token_header_and_parses_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["token"] = request.headers.get("X-Agent-Token")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "ok": True,
                "template_path": "/abs/templates/foo.hwp",
                "output_path": "/abs/output/out.hwp",
                "placeholders": ["{{company_name}}", "{{ceo_name}}"],
                "replaced": ["company_name", "ceo_name"],
                "missing": [],
                "remaining_placeholders": [],
            },
        )

    client = _make_client(handler, token="secret-123")
    outcome = client.autofill_bid_form(
        template_path="templates/foo.hwp",
        output_path="output/out.hwp",
        values={"company_name": "미림", "ceo_name": "홍길동"},
        visible=False,
    )

    assert isinstance(outcome, AutofillOutcome)
    assert captured["path"] == "/bid-form/autofill"
    assert captured["token"] == "secret-123"
    assert captured["body"]["values"]["company_name"] == "미림"
    assert outcome.replaced == ["company_name", "ceo_name"]
    assert outcome.missing == []
    assert outcome.remaining_placeholders == []


def test_autofill_raises_on_4xx_missing_values():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": {
                    "message": "Missing required bid form values.",
                    "missing": ["company_name"],
                    "placeholders": ["{{company_name}}"],
                }
            },
        )

    client = _make_client(handler)
    with pytest.raises(HwpAgentError) as exc_info:
        client.autofill_bid_form(
            template_path="t.hwp",
            output_path="o.hwp",
            values={},
        )
    assert "422" in str(exc_info.value)


def test_put_fields_calls_serialized_worker_endpoint():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "output_path": "output/result.hwp",
                "replaced": ["notice_no"],
                "missing": ["ceo_name"],
                "remaining_placeholders": ["address"],
            },
        )

    client = _make_client(handler)
    outcome = client.put_fields(
        template_path="templates/form.hwp",
        output_path="output/result.hwp",
        values={"notice_no": "SPEC-1"},
        visible=True,
    )

    assert isinstance(outcome, PutFieldsOutcome)
    assert captured["path"] == "/document/put-fields"
    assert captured["body"] == {
        "template_path": "templates/form.hwp",
        "output_path": "output/result.hwp",
        "values": {"notice_no": "SPEC-1"},
        "visible": True,
    }
    assert outcome.missing == ["ceo_name"]
    assert outcome.remaining_placeholders == ["address"]


def test_request_retries_transport_error_then_succeeds():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectError("simulated")
        return httpx.Response(200, json={"ok": True})

    client = _make_client(handler)
    assert client.health() is True
    assert attempts["n"] == 2


def test_request_raises_after_exhausting_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("always fails")

    client = _make_client(handler)
    # health() swallows errors and returns False
    assert client.health() is False

    # direct call surfaces HwpAgentError
    with pytest.raises(HwpAgentError):
        client.analyze_document("templates/foo.hwp")


def test_connect_failure_gives_actionable_message():
    """연결 자체가 안 되면 '[Errno 101]...' 대신 actionable 메시지로 치환한다."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 101] Network is unreachable")

    client = _make_client(handler)
    with pytest.raises(HwpAgentError) as exc_info:
        client.analyze_document("templates/foo.hwp")
    msg = str(exc_info.value)
    assert "연결할 수 없습니다" in msg
    assert "http://hwp-agent.test" in msg


def test_rag_search_filters_non_dict_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "query": "q",
                "results": [
                    {"source_path": "data/products/a.json", "score": 1.2},
                    "garbage",
                    None,
                    {"source_path": "data/proposals/b.md", "score": 0.9},
                ],
            },
        )

    client = _make_client(handler)
    results = client.rag_search("modbus", limit=4)
    assert len(results) == 2
    assert results[0]["source_path"] == "data/products/a.json"


def test_analyze_document_passes_path():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "ok": True,
                "stats": {"placeholders": 2},
                "placeholders": ["{{company_name}}", "{{ceo_name}}"],
            },
        )

    client = _make_client(handler)
    body = client.analyze_document("templates/입찰참가신청서_양식.hwp")
    assert captured["body"] == {"path": "templates/입찰참가신청서_양식.hwp"}
    assert body["placeholders"] == ["{{company_name}}", "{{ceo_name}}"]
