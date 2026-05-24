"""기존 bids.specs_json 에서 새 컬럼 값을 추출해 backfill.

PR 2 마이그레이션 0005 이후 한 번 실행. 멱등 — 이미 컬럼에 값이 있으면 skip
(--force 옵션으로 덮어쓰기 가능).

Usage:
    python -m scripts.backfill_bid_fields --dry-run            # 변경 없이 카운트만
    python -m scripts.backfill_bid_fields                       # 실제 update
    python -m scripts.backfill_bid_fields --force --batch-size=200

매핑 (specs_json 한국어 키 → Bid 컬럼):
    기초금액           → base_price
    추정가격           → estimated_price (기존 G2B 값 우선)
    낙찰하한율         → nakchal_lower_rate
    입찰방식           → tender_type
    낙찰자선정방식     → evaluation_method
    조달청물품분류번호 → product_classification_code
    직접생산증명요구   → requires_direct_manufacturing
    위임장허용         → accepts_distributor_loa
    적격심사_배점      → eligibility_weights
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from src.db.repository import AsyncSessionLocal  # noqa: E402
from src.db.models import Bid  # noqa: E402
from src.llm.structured_output import _to_optional_float, _normalize_nakchal_rate  # noqa: E402


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill")


_TENDER_TYPES = {"일반경쟁", "제한경쟁", "협상에의한계약", "수의계약", "MAS", "지명경쟁"}
_EVAL_METHODS = {"적격심사", "종합평가", "최저가", "협상", "2단계경쟁"}


def _coerce_str(v: Any, allowed: set[str] | None = None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if allowed is not None and s not in allowed:
        return None
    return s


def _coerce_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y", "예", "허용", "필요"):
        return True
    if s in ("false", "0", "no", "n", "아니오", "비허용", "불필요", ""):
        return False
    return None


def _to_decimal(v) -> Decimal | None:
    f = _to_optional_float(v)
    if f is None:
        return None
    try:
        return Decimal(str(f))
    except InvalidOperation:
        return None


def _extract_updates(bid: Bid, force: bool) -> dict[str, Any]:
    """specs_json 에서 추출한 컬럼 update 후보 반환. 변경할 필드만 키로 포함."""
    specs: dict = bid.specs_json or {}
    updates: dict[str, Any] = {}

    def maybe(col: str, new_value):
        if new_value is None:
            return
        current = getattr(bid, col)
        if current is not None and not force:
            return
        if current == new_value:
            return
        updates[col] = new_value

    maybe("base_price", _to_decimal(specs.get("기초금액")))
    # estimated_price 는 G2B collector 가 직접 채워뒀을 수 있으므로 force 가 아니면 덮지 않음.
    maybe("estimated_price", _to_decimal(specs.get("추정가격")))

    rate = _normalize_nakchal_rate(specs.get("낙찰하한율"))
    if rate is not None:
        rate_dec = Decimal(str(rate)).quantize(Decimal("0.00001"))
        maybe("nakchal_lower_rate", rate_dec)

    maybe("tender_type", _coerce_str(specs.get("입찰방식"), allowed=_TENDER_TYPES))
    maybe("evaluation_method", _coerce_str(specs.get("낙찰자선정방식"), allowed=_EVAL_METHODS))
    maybe("product_classification_code", _coerce_str(specs.get("조달청물품분류번호")))

    direct = _coerce_bool(specs.get("직접생산증명요구"))
    if direct is not None:
        # bool 컬럼은 False 가 default 라 _maybe 로직과 다르게 명시적 True/False 모두 반영
        if force or bid.requires_direct_manufacturing != direct:
            updates["requires_direct_manufacturing"] = direct

    loa = _coerce_bool(specs.get("위임장허용"))
    if loa is not None:
        if force or bid.accepts_distributor_loa != loa:
            updates["accepts_distributor_loa"] = loa

    weights = specs.get("적격심사_배점")
    if isinstance(weights, dict) and weights:
        # 값을 float 로 강제
        try:
            normalized = {str(k): float(v) for k, v in weights.items()}
            maybe("eligibility_weights", normalized)
        except (TypeError, ValueError):
            pass

    return updates


async def run(dry_run: bool, force: bool, batch_size: int) -> int:
    processed = 0
    updated = 0
    skipped_no_specs = 0
    extraction_failures = 0
    offset = 0

    async with AsyncSessionLocal() as session:
        while True:
            result = await session.execute(
                select(Bid).order_by(Bid.id).limit(batch_size).offset(offset)
            )
            batch = list(result.scalars().all())
            if not batch:
                break

            for bid in batch:
                processed += 1
                if not bid.specs_json:
                    skipped_no_specs += 1
                    continue
                try:
                    updates = _extract_updates(bid, force=force)
                except Exception:
                    extraction_failures += 1
                    logger.exception("extract failed for bid id=%s", bid.id)
                    continue
                if updates:
                    if not dry_run:
                        for col, value in updates.items():
                            setattr(bid, col, value)
                    updated += 1
                    logger.debug("bid %s: %s", bid.id, list(updates.keys()))

            if not dry_run:
                await session.commit()
            offset += batch_size

    logger.info(
        "summary: processed=%d updated=%d skipped_no_specs=%d failed=%d (dry_run=%s, force=%s)",
        processed, updated, skipped_no_specs, extraction_failures, dry_run, force,
    )
    return 0 if extraction_failures == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="DB 변경 없이 카운트만")
    ap.add_argument("--force", action="store_true", help="이미 값이 있는 컬럼도 덮어쓰기")
    ap.add_argument("--batch-size", type=int, default=500, help="row 페이지 크기")
    args = ap.parse_args()
    return asyncio.run(run(args.dry_run, args.force, args.batch_size))


if __name__ == "__main__":
    sys.exit(main())
