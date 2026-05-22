"""낙찰(BidAward) 와 Bid 를 source_id 기준으로 연결. 주간 수집 직후 + 매시간 sweep."""
import logging
from sqlalchemy import select, update
from src.db.repository import AsyncSessionLocal
from src.db.models import Bid, BidAward
from src.collector.base import RawAward

logger = logging.getLogger(__name__)


async def save_awards(raw_awards: list[RawAward]) -> int:
    """RawAward 들을 BidAward 로 저장 (이미 있으면 skip).
    매칭되는 Bid 가 있으면 bid_id + award_ratio 채움, 없으면 NULL 로 두고 나중에 링크."""
    if not raw_awards:
        return 0
    saved = 0
    async with AsyncSessionLocal() as session:
        for ra in raw_awards:
            existing = (await session.execute(
                select(BidAward).where(BidAward.source_award_id == ra.source_award_id)
            )).scalar_one_or_none()
            if existing:
                continue

            bid = None
            if ra.source_bid_id:
                bid = (await session.execute(
                    select(Bid).where(Bid.source == ra.source, Bid.source_id == ra.source_bid_id)
                )).scalar_one_or_none()

            ratio = None
            if bid and bid.estimated_price and ra.award_price:
                ratio = float(ra.award_price) / float(bid.estimated_price)

            award = BidAward(
                bid_id=bid.id if bid else None,
                source=ra.source,
                source_award_id=ra.source_award_id,
                source_bid_id=ra.source_bid_id,
                winner_name=ra.winner_name,
                winner_biz_no=ra.winner_biz_no,
                award_price=ra.award_price,
                award_date=ra.award_date,
                participant_count=ra.participant_count,
                award_ratio=ratio,
                raw_json=ra.raw,
            )
            session.add(award)
            if bid:
                bid.award_status = "awarded"
            saved += 1
        await session.commit()
    logger.info("BidAward 저장: %s건", saved)
    return saved


async def link_orphan_awards() -> int:
    """bid_id=NULL 인 BidAward 들을 source_bid_id 로 다시 매칭 시도."""
    linked = 0
    async with AsyncSessionLocal() as session:
        orphans = (await session.execute(
            select(BidAward).where(BidAward.bid_id.is_(None), BidAward.source_bid_id.is_not(None))
        )).scalars().all()

        for award in orphans:
            bid = (await session.execute(
                select(Bid).where(Bid.source == award.source, Bid.source_id == award.source_bid_id)
            )).scalar_one_or_none()
            if not bid:
                continue
            award.bid_id = bid.id
            if bid.estimated_price and award.award_price:
                award.award_ratio = float(award.award_price) / float(bid.estimated_price)
            await session.execute(
                update(Bid).where(Bid.id == bid.id).values(award_status="awarded")
            )
            linked += 1
        await session.commit()
    if linked:
        logger.info("link_orphan_awards: %s건 연결", linked)
    return linked


async def weekly_award_collection() -> None:
    """주간 잡: 최근 14일 G2B 낙찰 수집 + linker."""
    from datetime import datetime, timedelta
    from src.collector.g2b_award import G2BAwardCollector
    date_to = datetime.utcnow()
    date_from = date_to - timedelta(days=14)
    raws = await G2BAwardCollector().collect(date_from, date_to)
    if raws:
        await save_awards(raws)
        await link_orphan_awards()
