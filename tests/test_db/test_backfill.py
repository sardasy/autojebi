"""PR 2: backfill 스크립트 — specs_json → 새 컬럼."""
import asyncio
import sys
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.db.repository import AsyncSessionLocal
from src.db.models import Bid
from scripts.backfill_bid_fields import run as backfill_run


# 테스트 marker — 실제 DB 가 필요
pytestmark = pytest.mark.asyncio


async def _make_bid(specs_json: dict, **overrides) -> uuid.UUID:
    bid_id = uuid.uuid4()
    base = dict(
        id=bid_id,
        source="test_backfill",
        source_id=f"TEST-BACKFILL-{bid_id.hex[:8]}",
        title=f"backfill 테스트 {bid_id.hex[:6]}",
        specs_json=specs_json,
    )
    base.update(overrides)
    async with AsyncSessionLocal() as session:
        session.add(Bid(**base))
        await session.commit()
    return bid_id


async def _cleanup(bid_ids: list[uuid.UUID]):
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Bid).where(Bid.id.in_(bid_ids)))
        await session.commit()


async def _fetch(bid_id: uuid.UUID) -> Bid:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Bid).where(Bid.id == bid_id))
        return res.scalar_one()


async def test_backfill_extracts_base_price():
    bid_id = await _make_bid({
        "기초금액": 850000000,
        "낙찰하한율": 0.87745,
        "입찰방식": "일반경쟁",
        "낙찰자선정방식": "적격심사",
        "조달청물품분류번호": "26111703",
    })
    try:
        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid = await _fetch(bid_id)
        assert bid.base_price == Decimal("850000000.00")
        assert bid.nakchal_lower_rate == Decimal("0.87745")
        assert bid.tender_type == "일반경쟁"
        assert bid.evaluation_method == "적격심사"
        assert bid.product_classification_code == "26111703"
    finally:
        await _cleanup([bid_id])


async def test_backfill_idempotent():
    bid_id = await _make_bid({
        "기초금액": 500000000,
        "입찰방식": "제한경쟁",
    })
    try:
        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid1 = await _fetch(bid_id)
        first_base = bid1.base_price

        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid2 = await _fetch(bid_id)
        # 같은 값 유지 — 멱등
        assert bid2.base_price == first_base
        assert bid2.tender_type == "제한경쟁"
    finally:
        await _cleanup([bid_id])


async def test_backfill_force_overwrites():
    bid_id = await _make_bid({
        "기초금액": 100000000,
        "입찰방식": "일반경쟁",
    })
    try:
        # 1차 — 100M / 일반경쟁
        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid1 = await _fetch(bid_id)
        assert bid1.base_price == Decimal("100000000.00")

        # specs_json 변경
        async with AsyncSessionLocal() as session:
            bid = (await session.execute(select(Bid).where(Bid.id == bid_id))).scalar_one()
            bid.specs_json = {"기초금액": 200000000, "입찰방식": "제한경쟁"}
            await session.commit()

        # force 없이 → 안 덮어쓰임
        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid2 = await _fetch(bid_id)
        assert bid2.base_price == Decimal("100000000.00")

        # force=True → 덮어씀
        await backfill_run(dry_run=False, force=True, batch_size=100)
        bid3 = await _fetch(bid_id)
        assert bid3.base_price == Decimal("200000000.00")
        assert bid3.tender_type == "제한경쟁"
    finally:
        await _cleanup([bid_id])


async def test_nakchal_rate_normalization():
    bid_id = await _make_bid({"낙찰하한율": 87.745})  # 퍼센트 표기
    try:
        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid = await _fetch(bid_id)
        assert bid.nakchal_lower_rate == Decimal("0.87745")
    finally:
        await _cleanup([bid_id])


async def test_backfill_dry_run_no_changes():
    bid_id = await _make_bid({"기초금액": 999000000})
    try:
        await backfill_run(dry_run=True, force=False, batch_size=100)
        bid = await _fetch(bid_id)
        assert bid.base_price is None  # dry-run → DB 미변경
    finally:
        await _cleanup([bid_id])


async def test_eligibility_weights_extracted():
    bid_id = await _make_bid({
        "적격심사_배점": {"납품실적": 30, "경영상태": 30, "기술능력": 10, "입찰가격": 30}
    })
    try:
        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid = await _fetch(bid_id)
        assert bid.eligibility_weights == {
            "납품실적": 30.0, "경영상태": 30.0, "기술능력": 10.0, "입찰가격": 30.0,
        }
    finally:
        await _cleanup([bid_id])


async def test_boolean_flags_backfilled():
    bid_id = await _make_bid({
        "직접생산증명요구": True,
        "위임장허용": True,
    })
    try:
        await backfill_run(dry_run=False, force=False, batch_size=100)
        bid = await _fetch(bid_id)
        assert bid.requires_direct_manufacturing is True
        assert bid.accepts_distributor_loa is True
    finally:
        await _cleanup([bid_id])
