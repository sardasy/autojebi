"""나라장터(G2B) OpenAPI 클라이언트.

data.go.kr 입찰공고정보서비스 — 5종 PPSSrch (service/goods/construction/foreign/etc).
abb-bid-pipeline의 app/collector/g2b_client.py를 이식. 자격(qualification) 엔드포인트는
M3에서 그레이딩 도입할 때 부활. 현재는 수집(collect_range)만 사용한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import unquote, urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from api.config import settings


def _iter_windows(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        chunk_end = min(end, cur + timedelta(days=max_days - 1))
        out.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return out


def _dedupe_by_bid_key(bids: list[RawBid]) -> list[RawBid]:
    """(bid_no, bid_seq) 쌍 기준 dedup — 페이지·키워드·엔드포인트 중복 방어.

    G2B 응답이 같은 공고를 여러 페이지/엔드포인트에 걸쳐 반환할 수 있으므로 항상 적용.
    """
    seen: set[tuple[str, str]] = set()
    out: list[RawBid] = []
    for b in bids:
        key = (b.bid_no, b.bid_seq)
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out


def _normalize_service_key(raw: str) -> str:
    """data.go.kr 키가 URL-인코딩(%2F 등) 형태로 들어와도 디코딩.

    urlencode가 자동으로 다시 인코딩하므로 raw('/', '+', '=' 포함) 형태가 정상 입력이다.
    디코딩 후에도 '%'가 남아 있으면 비정상으로 보고 원본 반환.
    """
    if "%" not in raw:
        return raw
    decoded = unquote(raw)
    if "%" in decoded:
        return raw
    return decoded


log = logging.getLogger(__name__)

_BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"

_ENDPOINTS: list[tuple[str, str]] = [
    ("service",      "/getBidPblancListInfoServcPPSSrch"),
    ("goods",        "/getBidPblancListInfoThngPPSSrch"),
    ("construction", "/getBidPblancListInfoCnstwkPPSSrch"),
    ("foreign",      "/getBidPblancListInfoFrgcptPPSSrch"),
    ("etc",          "/getBidPblancListInfoEtcPPSSrch"),
]

# M5 부활 — 자격(면허제한·참가가능지역) 별도 엔드포인트
_LICENSE_LIMIT_PATH = "/getBidPblancListInfoLicenseLimit"
_PRTCPT_PSBL_RGN_PATH = "/getBidPblancListInfoPrtcptPsblRgn"

_PAGE_SIZE = 100
_MAX_RANGE_DAYS = 30  # G2B PPSSrch inqryDiv=1 모드의 31일 제한 회피

MATCH_FIELDS: tuple[str, ...] = (
    "bidNtceNm",
    "ntceSpecFileNm1", "ntceSpecFileNm2", "ntceSpecFileNm3",
    "ntceSpecFileNm4", "ntceSpecFileNm5",
    "bidQlfctRgstCntnts",
    "rmrkCntnts",
)


def keyword_variants(q: str) -> list[str]:
    """검색어를 띄어쓰기 변형으로 확장. 짧거나 이미 공백이 있으면 원본만."""
    base = q.strip()
    if not base:
        return []
    out: list[str] = [base]
    if " " in base or not (4 <= len(base) <= 12):
        return out
    seen = {base}
    for i in (2, 3, 4):
        if 0 < i < len(base):
            v = base[:i] + " " + base[i:]
            if v not in seen:
                out.append(v)
                seen.add(v)
    return out


def keyword_queries(q: str) -> list[str]:
    """G2B API에 던질 검색어 후보.

    나라장터 화면의 AND 검색은 토큰 순서가 바뀐 제목도 잡지만, PPSSrch의
    bidNtceNm 파라미터는 문구 순서에 민감하다. 공백 검색어는 원문 + 각 토큰을
    조회한 뒤 로컬에서 AND 필터링한다.
    """
    base = q.strip()
    if not base:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for candidate in [base, *keyword_variants(base)]:
        if candidate and candidate not in seen:
            out.append(candidate)
            seen.add(candidate)

    tokens = [t for t in re.split(r"\s+", base) if len(t) >= 2]
    if len(tokens) >= 2:
        longest = max(tokens, key=len)
        if longest not in seen:
            out.append(longest)
    return out


def _norm_search_text(value: object) -> str:
    return str(value or "").lower().replace(" ", "")


def _keyword_tokens(q: str) -> list[str]:
    return [_norm_search_text(t) for t in re.split(r"\s+", q.strip()) if t.strip()]


def match_all_tokens(raw: dict, keyword: str) -> bool:
    """MATCH_FIELDS 전체에서 keyword의 모든 토큰이 포함되는지 확인."""
    tokens = _keyword_tokens(keyword)
    if len(tokens) <= 1:
        return True
    haystack = " ".join(_norm_search_text(raw.get(fld)) for fld in MATCH_FIELDS)
    return all(token in haystack for token in tokens)


def match_raw(raw: dict, needles: list[str]) -> tuple[bool, str | None]:
    if not needles:
        return False, None
    for fld in MATCH_FIELDS:
        text = str(raw.get(fld, "") or "")
        if not text:
            continue
        for n in needles:
            if n and n in text:
                return True, fld
    return False, None


@dataclass
class RawBid:
    bid_no: str
    bid_seq: str
    title: str
    bid_type: str
    org_code: str
    org_name: str
    base_price: str | None
    open_date: str | None        # "YYYYMMDDHHMMSS"
    close_date: str | None
    detail_url: str | None
    raw: dict = field(default_factory=dict)


class G2BClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._key = _normalize_service_key(api_key or settings.data_go_kr_api_key)
        self._client = httpx.AsyncClient(timeout=30)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> G2BClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def collect_range(
        self,
        start: date,
        end: date,
        keywords: list[str] | None = None,
    ) -> list[RawBid]:
        keywords = keywords or settings.keyword_list
        results: list[RawBid] = []
        for kw in keywords:
            items = await self.search_single(start, end, kw)
            results.extend(items)

        deduped = _dedupe_by_bid_key(results)
        log.info("[G2B] 총 %d건 수집 (중복 제거 후)", len(deduped))
        return deduped

    async def search_single(
        self,
        start: date,
        end: date,
        keyword: str,
    ) -> list[RawBid]:
        """단일 키워드를 5개 PPSSrch 엔드포인트와 30일 윈도우에 걸쳐 조회.

        라이브 검색(POST /notices/search)의 백엔드 구현체. collect_range도 이 함수를
        키워드 루프로 감싸 재사용한다.

        병렬화 설계: 외부=윈도우 / 내부=엔드포인트로 정렬한 뒤, 윈도우 안의 5엔드포인트만
        asyncio.gather로 동시 호출. 윈도우 사이는 순차 (G2B 동시 호출 수를 5로 제한).
        365일 검색 시 13윈도우 × 5엔드포인트 = 65호출이 ~13라운드로 완료.

        동일 (bid_no, bid_seq) 쌍은 함수 내부에서 dedup.
        """
        t0 = time.monotonic()
        items: list[RawBid] = []
        queries = keyword_queries(keyword)
        for sub_start, sub_end in _iter_windows(start, end, _MAX_RANGE_DAYS):
            for query in queries:
                endpoint_results = await asyncio.gather(*[
                    self._fetch_all(path, bid_type, sub_start, sub_end, query)
                    for bid_type, path in _ENDPOINTS
                ])
                for page_items in endpoint_results:
                    items.extend(page_items)
        deduped = _dedupe_by_bid_key(items)
        if len(_keyword_tokens(keyword)) > 1:
            deduped = [bid for bid in deduped if match_all_tokens(bid.raw, keyword)]
        log.info(
            "[G2B] search '%s' (%s~%s, %d queries): %d items, %.1fs",
            keyword, start, end, len(queries), len(deduped), time.monotonic() - t0,
        )
        return deduped

    async def _fetch_all(
        self,
        path: str,
        bid_type: str,
        start: date,
        end: date,
        keyword: str | None,
    ) -> list[RawBid]:
        page, items = 1, []
        while True:
            batch = await self._fetch_page(path, bid_type, start, end, keyword, page)
            if not batch:
                break
            items.extend(batch)
            if len(batch) < _PAGE_SIZE:
                break
            page += 1
        return items

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _fetch_page(
        self,
        path: str,
        bid_type: str,
        start: date,
        end: date,
        keyword: str | None,
        page: int,
    ) -> list[RawBid]:
        params: dict[str, str | int] = {
            "serviceKey": self._key,
            "numOfRows": _PAGE_SIZE,
            "pageNo": page,
            "type": "json",
            "inqryDiv": "1",
            "inqryBgnDt": start.strftime("%Y%m%d") + "0000",
            "inqryEndDt": end.strftime("%Y%m%d") + "2359",
        }
        if keyword:
            params["bidNtceNm"] = keyword
        url = _BASE + path + "?" + urlencode(params)
        resp = await self._client.get(url)
        resp.raise_for_status()
        body = json.loads(resp.content.decode("utf-8-sig"))
        return self._parse(body, bid_type)

    @staticmethod
    def _parse(body: dict, bid_type: str) -> list[RawBid]:
        try:
            items = body["response"]["body"]["items"]
        except (KeyError, TypeError):
            return []
        if not items:
            return []
        if isinstance(items, dict):
            item_val = items.get("item", {})
        elif isinstance(items, list):
            item_val = items
        else:
            return []
        if isinstance(item_val, list):
            raw_list = item_val
        elif isinstance(item_val, dict):
            raw_list = [item_val]
        else:
            return []

        bids = []
        for it in raw_list:
            if not isinstance(it, dict):
                continue
            bid_no = str(it.get("bidNtceNo", "")).strip()
            bid_seq = str(it.get("bidNtceOrd", "00")).strip()
            if not bid_no:
                continue
            bids.append(
                RawBid(
                    bid_no=bid_no,
                    bid_seq=bid_seq,
                    title=str(it.get("bidNtceNm", "")).strip(),
                    bid_type=bid_type,
                    org_code=str(it.get("dminsttCd", "")).strip(),
                    org_name=str(it.get("ntceInsttNm", "")).strip(),
                    base_price=it.get("presmptPrce") or it.get("asignBdgtAmt"),
                    open_date=it.get("bidNtceDt"),
                    close_date=it.get("bidClseDt"),
                    detail_url=it.get("bidNtceUrl"),
                    raw=it,
                )
            )
        return bids

    # ------------------------------------------------------------------
    # M5: G2B 자격(면허·지역) API 라이브 호출
    # ------------------------------------------------------------------
    async def fetch_qualifications(self, bid_no: str, bid_seq: str):
        """LicenseLimit + PrtcptPsblRgn 두 API를 호출해 자격 정보를 통합한다.

        실패 시 QualificationInfo(error=...)를 반환 (예외 안 던짐) — 호출자(grading_runner)는
        raw_json 휴리스틱으로 폴백한다.
        """
        from api.grading.schemas import QualificationInfo

        try:
            lic_items = await self._fetch_qual_endpoint(_LICENSE_LIMIT_PATH, bid_no, bid_seq)
            rgn_items = await self._fetch_qual_endpoint(_PRTCPT_PSBL_RGN_PATH, bid_no, bid_seq)
        except Exception as exc:  # noqa: BLE001
            log.warning("[G2B] fetch_qualifications 실패 %s-%s: %s", bid_no, bid_seq, exc)
            return QualificationInfo(bid_no=bid_no, bid_seq=bid_seq, error=str(exc)[:200])

        licenses: list[str] = []
        permitted: list[str] = []
        for it in lic_items:
            name = str(it.get("lcnsLmtNm", "")).strip()
            if name:
                licenses.append(name)
            perms = str(it.get("permsnIndstrytyList", "")).strip()
            if perms:
                permitted.append(perms)

        regions: list[str] = []
        for it in rgn_items:
            rn = str(it.get("prtcptPsblRgnNm", "")).strip()
            if rn:
                regions.append(rn)

        return QualificationInfo(
            bid_no=bid_no,
            bid_seq=bid_seq,
            regions=regions,
            licenses=licenses,
            permitted_industries=permitted,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _fetch_qual_endpoint(
        self, path: str, bid_no: str, bid_seq: str
    ) -> list[dict]:
        params = {
            "serviceKey": self._key,
            "numOfRows": 100,
            "pageNo": 1,
            "type": "json",
            "inqryDiv": "2",
            "bidNtceNo": bid_no,
            "bidNtceOrd": bid_seq,
        }
        url = _BASE + path + "?" + urlencode(params)
        resp = await self._client.get(url)
        resp.raise_for_status()
        body = resp.json()
        try:
            items = body["response"]["body"]["items"]
        except (KeyError, TypeError):
            return []
        if not items:
            return []
        if isinstance(items, dict):
            inner = items.get("item", [])
        else:
            inner = items
        if isinstance(inner, dict):
            return [inner]
        if isinstance(inner, list):
            return [it for it in inner if isinstance(it, dict)]
        return []

    @staticmethod
    def parse_price(raw: str | None) -> int | None:
        if not raw:
            return None
        cleaned = str(raw).replace(",", "").strip()
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    @staticmethod
    def parse_datetime(raw: str | None) -> str | None:
        """G2B 응답의 날짜 문자열 → ISO8601(+09:00) 문자열.

        두 포맷 모두 지원:
          - 'YYYYMMDDHHMMSS' (구분자 없음, 14자)
          - 'YYYY-MM-DD HH:MM:SS' (dash·공백·콜론, ≤19자)
        """
        if not raw:
            return None
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if len(digits) < 8:
            return None
        digits = digits.ljust(14, "0")
        d, t = digits[:8], digits[8:14]
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}T{t[:2]}:{t[2:4]}:{t[4:6]}+09:00"

    @staticmethod
    def normalize_org_type(org_name: str) -> str:
        name = org_name
        if any(k in name for k in ("교육청", "대학교", "대학원")):
            return "education"
        if any(k in name for k in ("주식회사", "공사", "공단", "연구원", "재단")):
            return "public_corp"
        if any(k in name for k in ("특별시", "광역시", "특별자치시", "도청", "군청", "구청")):
            return "local"
        if any(k in name for k in ("부", "처", "청", "위원회")):
            return "central"
        return "other"

    @staticmethod
    def normalize_region(org_name: str) -> str | None:
        regions = [
            "서울", "부산", "대구", "인천", "광주", "대전", "울산",
            "세종", "경기", "강원", "충북", "충남", "전북", "전남",
            "경북", "경남", "제주",
        ]
        for r in regions:
            if r in org_name:
                return r
        return None

    @staticmethod
    def make_detail_url(bid_no: str, bid_seq: str) -> str:
        return (
            f"https://www.g2b.go.kr:8101/ep/invitation/publish/"
            f"bidInfoDtl.do?bidno={bid_no}&bidSeq={bid_seq}"
        )

    @staticmethod
    def dump_raw(bid: RawBid) -> str:
        return json.dumps(bid.raw, ensure_ascii=False)
