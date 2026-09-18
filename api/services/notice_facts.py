"""Shared normalization for API and manually registered G2B facts."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

KST = timezone(timedelta(hours=9))


def normalize_notice_facts(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    result: dict[str, Any] = {}
    for target, keys in {
        "org_name": ("ntceInsttNm", "org_name"),
        "org_code": ("ntceInsttCd", "org_code"),
        "bid_no": ("bidNtceNo", "bid_no"),
        "bid_seq": ("bidNtceOrd", "bid_seq"),
    }.items():
        value = next((raw[k] for k in keys if raw.get(k) not in (None, "")), None)
        if value is not None:
            result[target] = str(value).strip()
    for target, key in (("close_date", "bidClseDt"), ("open_date", "opengDt")):
        value = raw.get(key) or raw.get(target)
        if value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("/", "-"))
                result[target] = parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)
            except ValueError:
                pass
    # Estimated price/budget is never a substitute for a published base price.
    value = raw.get("bssamt") or raw.get("base_price")
    if value is not None:
        try:
            amount = Decimal(str(value).replace(",", ""))
            result["base_price"] = float(amount) if amount.is_finite() and amount > 0 else None
        except InvalidOperation:
            pass
    return result
