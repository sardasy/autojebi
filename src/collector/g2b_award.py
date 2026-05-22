"""G2B 낙찰 결과 수집기.

data.go.kr 의 ScsbidInfoService (낙찰현황) 추정 — 실제 운영 전에 portal 에서
endpoint 명/필드명을 확인해야 한다 (settings.award_collection_enabled=False 기본).
파싱 함수 parse_award_item 은 추정 필드명을 사용하므로 실데이터로 재검증 필요.
"""
import asyncio
import logging
from datetime import date, datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.collector.base import RawAward
from src.config import settings

logger = logging.getLogger(__name__)

G2B_AWARD_BASE_URL = "http://apis.data.go.kr/1230000/ScsbidInfoService"
CATEGORY_ENDPOINTS = {
    "용역": "getScsbidListSttusServc",
    "공사": "getScsbidListSttusCnstwk",
    "물품": "getScsbidListSttusThng",
}


def parse_award_item(item: dict) -> RawAward | None:
    """추정 필드명을 RawAward 로 매핑. 실데이터 받으면 키 보정."""
    try:
        notice_no = item.get("bidNtceNo")
        award_id = item.get("scsbidNo") or item.get("opbdNo") or item.get("bidNtceNo")
        if not award_id:
            return None

        price_str = item.get("sucsfbidAmt") or item.get("opbdPrce") or "0"
        award_price = int(str(price_str).replace(",", "").replace("원", "").strip() or "0") or None

        award_date = None
        for k in ("opbdDt", "sucsfbidDt", "rlOpengDt"):
            v = item.get(k, "")
            if v:
                try:
                    award_date = datetime.strptime(v[:10], "%Y/%m/%d").date()
                    break
                except ValueError:
                    try:
                        award_date = date.fromisoformat(v[:10])
                        break
                    except ValueError:
                        pass

        participant_count = None
        n = item.get("prtcptCnum") or item.get("prtcpCorpCnt")
        if n is not None:
            try:
                participant_count = int(n)
            except (TypeError, ValueError):
                pass

        return RawAward(
            source="g2b",
            source_award_id=str(award_id),
            source_bid_id=str(notice_no) if notice_no else None,
            winner_name=item.get("sucsfCorpNm") or item.get("opbdCorpNm"),
            winner_biz_no=item.get("sucsfCorpBizrno") or item.get("opbdCorpBizrno"),
            award_price=award_price,
            award_date=award_date,
            participant_count=participant_count,
            raw=item,
        )
    except Exception as e:
        logger.debug("G2B 낙찰 항목 파싱 실패: %s", e)
        return None


class G2BAwardCollector:
    def __init__(self):
        self.api_key = settings.data_go_kr_api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_page(self, client: httpx.AsyncClient, endpoint: str, params: dict) -> dict:
        service_key = params.pop("ServiceKey", self.api_key)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{G2B_AWARD_BASE_URL}/{endpoint}?ServiceKey={service_key}&{query}"
        response = await client.get(url, timeout=30)
        if not response.is_success:
            logger.error("award API 오류 %s: %s", response.status_code, response.text[:500])
            response.raise_for_status()
        return response.json()

    async def collect(self, date_from: datetime, date_to: datetime) -> list[RawAward]:
        if not settings.award_collection_enabled:
            logger.info("award_collection_enabled=False, 낙찰 수집 건너뜀")
            return []
        if not self.api_key:
            logger.warning("나라장터 API 키 미설정, 낙찰 수집 건너뜀")
            return []

        results: list[RawAward] = []
        date_fmt = "%Y%m%d%H%M"

        async with httpx.AsyncClient() as client:
            for category, endpoint in CATEGORY_ENDPOINTS.items():
                try:
                    awards = await self._collect_category(client, endpoint, date_from, date_to, date_fmt)
                    results.extend(awards)
                    logger.info("G2B 낙찰 %s: %s건 수집", category, len(awards))
                except Exception as e:
                    logger.error("G2B 낙찰 %s 수집 실패: %s", category, e)

        return results

    async def _collect_category(self, client, endpoint, date_from, date_to, date_fmt) -> list[RawAward]:
        awards: list[RawAward] = []
        page = 1
        while True:
            params = {
                "inqryDiv": "1",
                "inqryBgnDt": date_from.strftime(date_fmt),
                "inqryEndDt": date_to.strftime(date_fmt),
                "pageNo": page,
                "numOfRows": 100,
                "type": "json",
            }
            data = await self._fetch_page(client, endpoint, params)
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item") or []
            if isinstance(items, dict):
                items = [items]
            if not items:
                break
            for item in items:
                a = parse_award_item(item)
                if a:
                    awards.append(a)
            if len(items) < 100:
                break
            page += 1
            await asyncio.sleep(0.5)
        return awards
