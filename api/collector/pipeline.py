"""G2B 수집 파이프라인 — RawBid를 bid_pipeline 테이블에 업서트.

abb-bid-pipeline은 정규화된 Organization+Bid+Supplier 3-테이블 비동기 모델이지만,
autojebi는 단일 bid_pipeline 테이블 + 명시적 상태머신을 유지한다 (M1 범위).
따라서 본 이식은 다음 두 가지를 한다:

  1. G2B의 (bid_no, bid_seq) 복합키를 autojebi의 단일 PK `notice_no = f"{bid_no}-{bid_seq}"`로 합성.
  2. 기존 [POST /notices/upsert]와 동일한 멱등성 규칙 — `status`는 절대 다운그레이드되지 않음.
     이미 analyzed/notified 상태인 공고가 재수집되어도 `collected`로 되돌아가지 않는다.

호출자 관점에서는 동기 함수. 내부에서는 asyncio.run()으로 G2B 비동기 클라이언트 구동.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from api.collector.g2b_client import G2BClient, RawBid
from api.models.notices import NoticeSearchItem, NoticeSearchResponse
from api.routers.notices import bid_pipeline

log = logging.getLogger(__name__)


def make_notice_no(bid_no: str, bid_seq: str) -> str:
    """abb-bid-pipeline의 복합키 (bid_no, bid_seq)를 autojebi의 단일 PK로 합성."""
    seq = (bid_seq or "00").strip() or "00"
    return f"{bid_no}-{seq}"


def run_collection(
    engine: Engine,
    start: date | None = None,
    end: date | None = None,
    keywords: list[str] | None = None,
) -> dict[str, int]:
    """동기 진입점 — scheduler와 trigger 라우터가 호출.

    내부에서 asyncio.run()으로 G2BClient(httpx.AsyncClient)를 구동.
    autojebi의 sync SQLAlchemy 모델과 호환된다.
    """
    today = date.today()
    start = start or today
    end = end or today

    raw_bids = asyncio.run(_collect_async(start, end, keywords))

    stats = {"fetched": len(raw_bids), "new": 0, "skipped": 0}
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        for raw in raw_bids:
            outcome = _upsert(conn, raw, now)
            stats[outcome] += 1

    log.info("[pipeline] G2B 수집 완료 — %s", stats)
    return stats


async def _collect_async(
    start: date,
    end: date,
    keywords: list[str] | None,
) -> list[RawBid]:
    async with G2BClient() as client:
        return await client.collect_range(start, end, keywords)


def _upsert(conn: Any, raw: RawBid, now: datetime) -> str:
    """raw 1건을 bid_pipeline에 업서트. 반환값은 stats 키 ('new' | 'skipped')."""
    notice_no = make_notice_no(raw.bid_no, raw.bid_seq)
    title = _clean_title(raw.title)

    open_dt = _parse_iso(G2BClient.parse_datetime(raw.open_date))
    close_dt = _parse_iso(G2BClient.parse_datetime(raw.close_date))
    base_price = G2BClient.parse_price(raw.base_price)

    stmt = insert(bid_pipeline).values(
        notice_no=notice_no,
        title=title,
        source="G2B",
        raw=raw.raw,
        category="비관련",
        fit_score=0,
        assignee="미배정",
        analysis={},
        status="collected",
        created_at=now,
        updated_at=now,
        bid_no=raw.bid_no,
        bid_seq=raw.bid_seq or "00",
        bid_type=raw.bid_type,
        org_code=raw.org_code or None,
        org_name=raw.org_name or None,
        base_price=base_price,
        open_date=open_dt,
        close_date=close_dt,
        collected_at=now,
    )

    # 멱등성: `status`는 절대 다운그레이드되지 않음. raw payload와 메타데이터만 갱신.
    # 정확한 상태 보존을 위해 status는 기존 컬럼값을 그대로 유지하도록 set하지 않는다.
    stmt = stmt.on_conflict_do_update(
        index_elements=[bid_pipeline.c.notice_no],
        set_={
            "title": stmt.excluded.title,
            "raw": stmt.excluded.raw,
            "bid_type": stmt.excluded.bid_type,
            "org_code": stmt.excluded.org_code,
            "org_name": stmt.excluded.org_name,
            "base_price": stmt.excluded.base_price,
            "open_date": stmt.excluded.open_date,
            "close_date": stmt.excluded.close_date,
            "updated_at": now,
        },
    ).returning(bid_pipeline.c.created_at)

    result = conn.execute(stmt).mappings().one()
    # 새 행이면 created_at == now (방금 INSERT됨). 기존 행이면 과거 created_at.
    if result["created_at"] == now:
        return "new"
    return "skipped"


def _clean_title(title: str) -> str:
    return title.replace("\n", " ").replace("\t", " ").strip()


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


# ── M13: G2B 라이브 검색 ──
#
# DB write 없음. G2B 검색 결과 + 동일 (source, notice_no) 존재 여부만 반환.
# 실제 저장은 프론트가 사용자 액션으로 POST /notices/upsert를 호출.


def search_notices(
    engine: Engine,
    start: date,
    end: date,
    keyword: str,
    page: int = 1,
    page_size: int = 50,
) -> NoticeSearchResponse:
    """G2B 라이브 검색 → 각 결과에 already_exists 플래그를 붙여 반환.

    keyword는 호출자(라우터)가 strip해서 비어 있지 않음을 보장.
    G2B HTTP 실패는 그대로 raise — 라우터에서 502로 변환.

    페이지네이션 정책:
      - G2B 전체 윈도우·엔드포인트 페치 + (bid_no, bid_seq) 중복 제거는 항상 수행.
      - total = dedup된 전체 개수. total_pages = ceil(total / page_size).
      - 그 후 [start_idx:end_idx] 슬라이스만 NoticeSearchItem으로 변환하고
        already_exists DB 조회도 슬라이스된 notice_no만 사용 (DB 부하 절감).
      - page가 total_pages를 초과해도 정상 응답 (빈 items + 정확한 meta).
    """
    raw_bids = asyncio.run(_search_async(start, end, keyword))

    total = len(raw_bids)
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_bids = raw_bids[start_idx:end_idx]

    items: list[NoticeSearchItem] = []
    notice_nos: list[str] = []
    for bid in page_bids:
        notice_no = make_notice_no(bid.bid_no, bid.bid_seq)
        notice_nos.append(notice_no)
        items.append(
            NoticeSearchItem(
                notice_no=notice_no,
                title=_clean_title(bid.title),
                source="G2B",
                org_name=bid.org_name or None,
                base_price=G2BClient.parse_price(bid.base_price),
                open_date=_parse_iso(G2BClient.parse_datetime(bid.open_date)),
                close_date=_parse_iso(G2BClient.parse_datetime(bid.close_date)),
                raw=bid.raw,
                already_exists=False,
            )
        )

    existing = _select_existing_notice_nos(engine, source="G2B", notice_nos=notice_nos)
    for item in items:
        if item.notice_no in existing:
            item.already_exists = True

    return NoticeSearchResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def _search_async(start: date, end: date, keyword: str) -> list[RawBid]:
    async with G2BClient() as client:
        return await client.search_single(start, end, keyword)


def _select_existing_notice_nos(
    engine: Engine,
    source: str,
    notice_nos: list[str],
) -> set[str]:
    """동일 source + notice_no 집합을 DB에서 조회."""
    if not notice_nos:
        return set()
    stmt = select(bid_pipeline.c.notice_no).where(
        bid_pipeline.c.source == source,
        bid_pipeline.c.notice_no.in_(notice_nos),
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).all()
    return {row[0] for row in rows}
