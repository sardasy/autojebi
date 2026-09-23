"""Time-sensitive checks for immutable asset snapshots used by document jobs."""
import re
from datetime import UTC, date, datetime, timedelta, timezone

from api.workspace.readiness_issues import IssueCode, issue

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
    code = document_issue_code(doc, company, on)
    return issue(code, "document").message if code else ""


def document_issue_code(doc: dict, company: dict | None = None, on: date | None = None) -> IssueCode | None:
    asset = doc.get("company_asset")
    if not asset:
        return None
    if asset.get("stale"):
        return IssueCode.ASSET_STALE
    state = validity(asset, on)
    if state not in {"valid", "expiring"}:
        return {"disabled": IssueCode.ASSET_DISABLED, "expired": IssueCode.ASSET_EXPIRED,
                "not_yet_valid": IssueCode.ASSET_NOT_YET_VALID}.get(state, IssueCode.ASSET_VALIDITY_UNKNOWN)
    if company is not None and doc.get("role") == "company_evidence":
        number = business_number(str(company.get("business_number") or ""))
        if not number or number != asset.get("subject_business_number"):
            return IssueCode.ASSET_SUBJECT_MISMATCH
    return None
