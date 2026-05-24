import logging
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from src.collector.base import BaseCollector, RawBid

logger = logging.getLogger(__name__)

KPX_BID_URL = "https://www.kpx.or.kr/www/contents.do?key=228"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.kpx.or.kr/",
}
_WAF_SIGNATURE = "contrary to the Web firewall"


class KPXScraper(BaseCollector):
    async def collect(self, date_from: datetime, date_to: datetime) -> list[RawBid]:
        results: list[RawBid] = []
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30, headers=_HEADERS
            ) as client:
                response = await client.get(KPX_BID_URL)
                response.raise_for_status()

                if _WAF_SIGNATURE in response.text:
                    logger.warning("KPX WAF 차단됨 — IP 허용 후 재시도 필요")
                    return []

                soup = BeautifulSoup(response.text, "lxml")
                # 실제 셀렉터는 JS 렌더링 이후 확인 필요 — 정적 HTML 대상 탐색
                rows = (
                    soup.select("table tbody tr")
                    or soup.select(".board-list tbody tr")
                    or soup.select(".tbl-wrap tbody tr")
                )

                for row in rows:
                    bid = self._parse_row(row)
                    if bid:
                        results.append(bid)

            logger.info(f"KPX: {len(results)}건 수집")
        except Exception:
            logger.exception("KPX 스크래핑 실패")

        return results

    def _parse_row(self, row) -> RawBid | None:
        try:
            cols = row.find_all("td")
            if len(cols) < 3:
                return None
            title_tag = cols[1].find("a") if len(cols) > 1 else None
            if not title_tag:
                return None
            return RawBid(
                source="kpx",
                source_id=f"kpx_{cols[0].get_text(strip=True)}",
                title=title_tag.get_text(strip=True),
                organization="전력거래소",
                category="용역",
                raw_content=title_tag.get_text(strip=True),
            )
        except Exception:
            return None

    async def get_detail(self, bid_id: str) -> str:
        return ""
