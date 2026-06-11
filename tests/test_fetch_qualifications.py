"""G2BClient.fetch_qualifications 단위 테스트 (M5).

httpx.AsyncClient는 mock — 실제 G2B API 호출 없음.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.collector.g2b_client import G2BClient


@pytest.mark.asyncio
async def test_fetch_qualifications_combines_license_and_region():
    license_body = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "lcnsLmtNm": "전기공사업/3001",
                            "permsnIndstrytyList": "[정보통신공사업/4001]",
                        },
                        {"lcnsLmtNm": "정보통신공사업/4001", "permsnIndstrytyList": ""},
                    ]
                }
            }
        }
    }
    region_body = {
        "response": {"body": {"items": {"item": {"prtcptPsblRgnNm": "서울특별시"}}}}
    }

    async def fake_get(url: str, **_kw):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(
            return_value=region_body if "PrtcptPsblRgn" in url else license_body
        )
        return resp

    client = G2BClient(api_key="dummy")
    client._client.get = AsyncMock(side_effect=fake_get)  # type: ignore[method-assign]
    try:
        info = await client.fetch_qualifications("R26BK01", "000")
    finally:
        await client.aclose()

    assert info.bid_no == "R26BK01"
    assert info.regions == ["서울특별시"]
    assert info.licenses == ["전기공사업/3001", "정보통신공사업/4001"]
    assert info.permitted_industries == ["[정보통신공사업/4001]"]
    assert info.error is None


@pytest.mark.asyncio
async def test_fetch_qualifications_empty_response_safe():
    async def fake_get(url: str, **_kw):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"response": {"body": {"items": ""}}})
        return resp

    client = G2BClient(api_key="dummy")
    client._client.get = AsyncMock(side_effect=fake_get)  # type: ignore[method-assign]
    try:
        info = await client.fetch_qualifications("X", "00")
    finally:
        await client.aclose()

    assert info.regions == []
    assert info.licenses == []
    assert info.error is None


@pytest.mark.asyncio
async def test_fetch_qualifications_http_error_records_error():
    client = G2BClient(api_key="dummy")
    client._client.get = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    try:
        info = await client.fetch_qualifications("X", "00")
    finally:
        await client.aclose()

    assert info.error is not None
    assert info.regions == []
    assert info.licenses == []


@pytest.mark.asyncio
async def test_fetch_qualifications_endpoints_called_with_inquiry_div_2():
    captured_urls: list[str] = []

    async def fake_get(url: str, **_kw):
        captured_urls.append(url)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"response": {"body": {"items": ""}}})
        return resp

    client = G2BClient(api_key="dummy")
    client._client.get = AsyncMock(side_effect=fake_get)  # type: ignore[method-assign]
    try:
        await client.fetch_qualifications("R26BK01", "000")
    finally:
        await client.aclose()

    assert len(captured_urls) == 2
    for url in captured_urls:
        assert "inqryDiv=2" in url
        assert "bidNtceNo=R26BK01" in url
        assert "bidNtceOrd=000" in url
