import logging
from datetime import datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.collector.base import BaseCollector, RawBid
from src.config import settings

logger = logging.getLogger(__name__)

KEPCO_BASE_URL = "http://openapi.kepco.co.kr/service/bidInfoService"


class KEPCOCollector(BaseCollector):
    def __init__(self):
        self.api_key = settings.kepco_api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch(self, client: httpx.AsyncClient, params: dict) -> dict:
        response = await client.get(f"{KEPCO_BASE_URL}/getBidSearchList", params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    async def collect(self, date_from: datetime, date_to: datetime) -> list[RawBid]:
        if not self.api_key:
            logger.warning("KEPCO API 키 미설정, 수집 건너뜀")
            return []

        results: list[RawBid] = []
        async with httpx.AsyncClient() as client:
            try:
                params = {
                    "serviceKey": self.api_key,
                    "startDate": date_from.strftime("%Y%m%d"),
                    "endDate": date_to.strftime("%Y%m%d"),
                    "pageNo": 1,
                    "numOfRows": 100,
                    "type": "json",
                }
                data = await self._fetch(client, params)
                items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
                if isinstance(items, dict):
                    items = [items]

                for item in items:
                    bid = self._parse_item(item)
                    if bid:
                        results.append(bid)

                logger.info(f"KEPCO: {len(results)}건 수집")
            except Exception as e:
                logger.error(f"KEPCO 수집 실패: {e}")

        return results

    def _parse_item(self, item: dict) -> RawBid | None:
        try:
            return RawBid(
                source="kepco",
                source_id=item.get("bidNo", ""),
                title=item.get("bidNm", ""),
                organization="한국전력공사",
                category=item.get("bidType", ""),
                raw_content=str(item),
                extra=item,
            )
        except Exception as e:
            logger.debug(f"KEPCO 항목 파싱 실패: {e}")
            return None

    async def get_detail(self, bid_id: str) -> str:
        return ""
