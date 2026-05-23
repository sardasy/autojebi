"""Concurrent save_awards must be idempotent on source_award_id (UNIQUE)."""
import asyncio
import sys
import uuid
import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.collector.award_linker import save_awards
from src.collector.base import RawAward
from src.db.repository import AsyncSessionLocal
from src.db.models import BidAward
from sqlalchemy import select, delete


def _make_raw(award_id: str) -> RawAward:
    return RawAward(
        source="g2b",
        source_award_id=award_id,
        source_bid_id=None,
        winner_name="테스트사",
        winner_biz_no="000-00-00000",
        award_price=100_000_000,
        award_date=None,
        participant_count=3,
        raw={"award_id": award_id},
    )


@pytest.mark.asyncio
async def test_save_awards_idempotent_under_concurrency():
    award_id = f"TEST-{uuid.uuid4().hex[:8]}"
    raws = [_make_raw(award_id)]

    try:
        # 동시 실행 — UNIQUE 위반 없이 한 번만 insert.
        results = await asyncio.gather(
            save_awards(raws), save_awards(raws), save_awards(raws)
        )
        assert sum(results) == 1, f"first call inserts 1, others get 0, got {results}"

        async with AsyncSessionLocal() as session:
            n = (await session.execute(
                select(BidAward).where(BidAward.source_award_id == award_id)
            )).scalars().all()
            assert len(n) == 1
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(BidAward).where(BidAward.source_award_id == award_id))
            await session.commit()
