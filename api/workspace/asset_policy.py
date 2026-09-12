"""Time-sensitive checks for immutable asset snapshots used by document jobs."""
import re
from datetime import UTC, date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def today() -> date:
    return datetime.now(UTC).astimezone(KST).date()


def business_number(value: str) -> str:
    return re.sub(r"[ -]", "", value)


def validity(details: dict, on: date | None = None) -> str:
    on = on or today()
    if not details.get("active", True):
        return "disabled"
    try:
        issued = date.fromisoformat(details["issued_on"]) if details.get("issued_on") else None
        expires = date.fromisoformat(details["expires_on"]) if details.get("expires_on") else None
    except (TypeError, ValueError):
        return "unknown"
    if issued and issued > on:
        return "not_yet_valid"
    if expires:
        if expires < on:
            return "expired"
        return "expiring" if expires <= on + timedelta(days=30) else "valid"
    return "valid" if details.get("no_expiry") else "unknown"


def document_issue(doc: dict, company: dict | None = None, on: date | None = None) -> str:
    asset = doc.get("company_asset")
    if not asset:
        return ""
    if asset.get("stale"):
        return "중앙 자료 변경: 다시 연결·검토 필요"
    state = validity(asset, on)
    if state not in {"valid", "expiring"}:
        return {"disabled":"중앙 자료 비활성", "expired":"중앙 자료 유효기간 만료",
                "not_yet_valid":"중앙 자료 발급일 미도래"}.get(state, "중앙 자료 유효기간 미확인")
    if company is not None and doc.get("role") == "company_evidence":
        number = business_number(str(company.get("business_number") or ""))
        if not number or number != asset.get("subject_business_number"):
            return "중앙 자료 회사 주체 불일치·미확인"
    return ""
