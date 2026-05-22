"""합성 낙찰 데이터로 award_linker 검증 (외부 API 없이).
실데이터 수집은 settings.award_collection_enabled=True + API 키 필요.
"""
import asyncio
import sys
import os
from datetime import date

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collector.base import RawAward  # noqa: E402
from src.collector.award_linker import save_awards, link_orphan_awards  # noqa: E402


SYNTHETIC = [
    RawAward(
        source="dummy",
        source_award_id="SCS-2026-001",
        source_bid_id="DUMMY-2026-001",
        winner_name="주식회사 가나전기",
        winner_biz_no="123-45-67890",
        award_price=722_000_000,
        award_date=date(2026, 6, 20),
        participant_count=4,
        raw={"note": "synthetic test"},
    ),
    RawAward(
        source="dummy",
        source_award_id="SCS-2026-002",
        source_bid_id="DUMMY-2026-002",
        winner_name="ESS 솔루션즈",
        winner_biz_no="234-56-78901",
        award_price=95_000_000,
        award_date=date(2026, 6, 18),
        participant_count=2,
        raw={"note": "synthetic test"},
    ),
    RawAward(
        source="dummy",
        source_award_id="SCS-2026-999",
        source_bid_id="DUMMY-NEVER-EXISTED",
        winner_name="주식회사 고아",
        award_price=10_000_000,
        award_date=date(2026, 6, 21),
        raw={"note": "orphan, no matching Bid"},
    ),
]


async def main():
    print(f"입력 RawAward: {len(SYNTHETIC)}건")
    n = await save_awards(SYNTHETIC)
    print(f"저장됨: {n}")
    linked = await link_orphan_awards()
    print(f"orphan 재링크: {linked}")


if __name__ == "__main__":
    asyncio.run(main())
