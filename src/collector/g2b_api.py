import asyncio
import logging
from datetime import datetime
from urllib.parse import urlencode
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.collector.base import BaseCollector, RawBid
from src.common.timez import kst_to_utc
from src.config import settings

logger = logging.getLogger(__name__)

G2B_BASE_URL = "http://apis.data.go.kr/1230000/BidPublicInfoService04"

CATEGORY_ENDPOINTS = {
    "용역": "getBidPblancListInfoServc",
    "공사": "getBidPblancListInfoCnstwk",
    "물품": "getBidPblancListInfoThng",
}


class G2BCollector(BaseCollector):
    def __init__(self):
        self.api_key = settings.data_go_kr_api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_page(self, client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
        service_key = params.pop("ServiceKey", self.api_key)
        # data.go.kr Encoding 인증키는 이미 percent-encoded — 더블 인코딩 회피 위해 raw 삽입.
        # 나머지 params 는 한글/특수문자 안전을 위해 urlencode.
        query = urlencode(params, doseq=True)
        url = f"{G2B_BASE_URL}/{endpoint}?ServiceKey={service_key}&{query}"
        response = await client.get(url, timeout=30)
        if not response.is_success:
            logger.error(f"API 오류 {response.status_code}: {response.text[:500]}")
            response.raise_for_status()
        return response.json()

    async def collect(self, date_from: datetime, date_to: datetime) -> list[RawBid]:
        if not self.api_key:
            logger.warning("나라장터 API 키 미설정, 수집 건너뜀")
            return []

        results: list[RawBid] = []
        date_fmt = "%Y%m%d%H%M"

        async with httpx.AsyncClient() as client:
            for category, endpoint in CATEGORY_ENDPOINTS.items():
                try:
                    bids = await self._collect_category(client, endpoint, category, date_from, date_to, date_fmt)
                    results.extend(bids)
                    logger.info(f"G2B {category}: {len(bids)}건 수집")
                except Exception:
                    logger.exception("G2B 수집 실패 (category=%s)", category)

        return results

    async def _collect_category(
        self, client, endpoint, category, date_from, date_to, date_fmt
    ) -> list[RawBid]:
        bids = []
        page = 1

        page_size = settings.g2b_page_size
        while True:
            params = {
                "inqryDiv": "1",
                "inqryBgnDt": date_from.strftime(date_fmt),
                "inqryEndDt": date_to.strftime(date_fmt),
                "pageNo": page,
                "numOfRows": page_size,
                "type": "json",
            }
            data = await self._fetch_page(client, endpoint, params)
            items = self._extract_items(data)
            if not items:
                break

            for item in items:
                bid = self._parse_item(item, category)
                if bid:
                    bids.append(bid)

            if len(items) < page_size:
                break
            page += 1
            await asyncio.sleep(settings.g2b_rate_limit_sleep)

        return bids

    def _extract_items(self, data: dict) -> list[dict]:
        try:
            items = data["response"]["body"]["items"]["item"]
            if isinstance(items, dict):
                return [items]
            return items or []
        except (KeyError, TypeError):
            return []

    def _parse_item(self, item: dict, category: str) -> RawBid | None:
        try:
            price_str = item.get("presmptPrce", "0") or "0"
            price = int(str(price_str).replace(",", "").replace("원", "").strip() or "0")

            deadline_str = item.get("bidClseDt", "")
            deadline = (
                kst_to_utc(datetime.strptime(deadline_str, "%Y/%m/%d %H:%M"))
                if deadline_str else None
            )

            announce_str = item.get("bidNtceDt", "")
            announce = (
                kst_to_utc(datetime.strptime(announce_str, "%Y/%m/%d %H:%M"))
                if announce_str else None
            )

            return RawBid(
                source="g2b",
                source_id=item.get("bidNtceNo", ""),
                title=item.get("bidNtceNm", ""),
                organization=item.get("ntceInsttNm", ""),
                category=category,
                estimated_price=price if price > 0 else None,
                deadline=deadline,
                announcement_date=announce,
                location=item.get("ntceInsttOfclNm", ""),
                raw_content=str(item),
                detail_url=item.get("bidNtceUrl", ""),
                extra=item,
            )
        except Exception as e:
            logger.debug(f"G2B 항목 파싱 실패: {e}")
            return None

    async def get_detail(self, bid_id: str) -> str:
        return ""
