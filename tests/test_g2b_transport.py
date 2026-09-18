import asyncio
from datetime import date

import httpx
import pytest

from api.collector.g2b_client import G2BClient, _normalize_service_key
from api.config import settings


@pytest.mark.parametrize("scheme", ["https", "http"])
def test_transport_scheme_and_single_key_encoding(monkeypatch, scheme):
    monkeypatch.setattr(settings, "g2b_api_scheme", scheme)

    async def run():
        client = G2BClient(api_key="  demo%2Bkey%2F%3D  ")
        assert client._client.timeout.connect == 8
        await client.aclose()

        def respond(request):
            assert request.url.scheme == scheme
            assert request.url.host == "apis.data.go.kr"
            assert request.url.params["ServiceKey"] == "demo+key/="
            assert "serviceKey" not in request.url.params
            assert request.url.params["inqryBgnDt"] == "202608120000"
            assert request.url.params["inqryEndDt"] == "202608122359"
            return httpx.Response(
                200, json={"response": {"header": {"resultCode": "00"}, "body": {"items": []}}}
            )

        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            assert (
                await client._fetch_page(
                    "/getBidPblancListInfoThngPPSSrch",
                    "goods",
                    date(2026, 8, 12),
                    date(2026, 8, 12),
                    "전자파 해석 SW",
                    1,
                )
                == []
            )
        finally:
            await client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("wire_format", ["json", "xml"])
@pytest.mark.parametrize(
    "code,exception,message",
    [
        ("30", PermissionError, "G2B_AUTH_FAILED"),
        ("22", ValueError, "G2B_RATE_LIMITED"),
        ("23", ValueError, "G2B_RATE_LIMITED"),
        ("29", ValueError, "G2B_IP_BLOCKED"),
        ("05", ValueError, "G2B_UPSTREAM_TIMEOUT"),
    ],
)
def test_gateway_errors_are_not_all_auth_errors(wire_format, code, exception, message):
    async def run():
        client = G2BClient(api_key="test-only")
        await client.aclose()

        def respond(request):
            if wire_format == "json":
                return httpx.Response(
                    200,
                    json={
                        "response": {
                            "header": {"resultCode": code, "resultMsg": "secret must not propagate"}
                        }
                    },
                )
            return httpx.Response(
                200,
                text=f"<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>{code}</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>",
            )

        client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(exception, match=f"^{message}$"):
                await client._fetch_page(
                    "/getBidPblancListInfoThngPPSSrch",
                    "goods",
                    date(2026, 8, 12),
                    date(2026, 8, 12),
                    "전자파",
                    1,
                )
        finally:
            await client.aclose()

    asyncio.run(run())


def test_key_whitespace_is_removed():
    assert _normalize_service_key("  demo+key/=\n") == "demo+key/="
