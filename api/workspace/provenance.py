"""Shared source/evidence checks for edits, readiness, and generated packages."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from api.workspace.asset_policy import document_issue

_NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
_KRW_AMOUNT = re.compile(
    rf"(?<![\w.,+\-/$€₩])(?:"
    rf"(?:KRW|₩)\s*(?P<prefix>{_NUMBER})(?:\s*원)?(?![\w,/%]|\.[0-9])"
    rf"|(?P<suffix>{_NUMBER})\s*원(?![0-9A-Za-z]))",
    re.IGNORECASE,
)


def price_amount_present(quote: str, offer_price: Any) -> bool:
    if not isinstance(quote, str) or isinstance(offer_price, bool):
        return False
    try:
        price = Decimal(str(offer_price))
    except InvalidOperation:
        return False
    if not price.is_finite() or price <= 0:
        return False
    # Require a complete KRW amount; signed, scaled and partial tokens are not evidence.
    for match in _KRW_AMOUNT.finditer(quote):
        preceding = quote[: match.start()].rstrip()
        if preceding.endswith(("-", "+", "$", "€", "/", ".", ",", "\u2212", "\uff0d", "\uff0b")):
            continue
        if match.group("suffix") and preceding[-1:].isdigit():
            continue
        if re.search(r"\b(?:USD|EUR|JPY|CNY|RMB|GBP)$", preceding, re.IGNORECASE):
            continue
        following = quote[match.end() :].lstrip()
        if (
            match.group("prefix")
            and not match.group().endswith("원")
            and re.match(r"[0-9%/]", following)
        ):
            continue
        if re.match(
            r"(?:thousand|million|billion|trillion|hundred|[kmbt]\b|[십백천만억조])",
            following,
            re.IGNORECASE,
        ):
            continue
        number = match.group("prefix") or match.group("suffix")
        if Decimal(number.replace(",", "")) == price:
            return True
    return False


def commercial_valid(commercial: dict, documents: dict[str, dict]) -> bool:
    document = documents.get(commercial.get("document_id")) or {}
    quote = commercial.get("quote")
    quantity = commercial.get("quantity")
    return bool(
        type(quantity) is int
        and quantity > 0
        and document.get("role") in {"company_evidence", "product_evidence"}
        and document.get("confirmed")
        and not document_issue(document)
        and isinstance(quote, str)
        and quote.strip()
        and quote in (document.get("text") or "")
        and str(commercial.get("locator") or "").strip()
        and str(commercial.get("note") or "").strip()
        and price_amount_present(quote, commercial.get("offer_price"))
    )


def source_quote_valid(requirement: dict, documents: dict[str, dict]) -> bool:
    source = documents.get(requirement.get("document_id")) or {}
    quote = str(requirement.get("quote") or "")
    return bool(
        source.get("role") == "notice_source"
        and quote.strip()
        and quote in (source.get("text") or "")
        and str(requirement.get("locator") or "").strip()
    )


def evidence_valid(requirement: dict, documents: dict[str, dict]) -> bool:
    evidence = documents.get(requirement.get("evidence_id")) or {}
    quote = str(requirement.get("evidence_quote") or "")
    return bool(
        evidence.get("role") in {"company_evidence", "product_evidence"}
        and evidence.get("confirmed")
        and not document_issue(evidence)
        and quote.strip()
        and quote in (evidence.get("text") or "")
        and str(requirement.get("evidence_locator") or "").strip()
        and str(requirement.get("proposed_value") or "").strip()
    )


def requirement_valid(requirement: dict, documents: dict[str, dict]) -> bool:
    return (
        requirement.get("review_status") == "accepted"
        and source_quote_valid(requirement, documents)
        and evidence_valid(requirement, documents)
    )


def section_valid(section: dict, inputs: dict) -> bool:
    documents = {d["id"]: d for d in inputs.get("documents") or []}
    requirements = {r["id"]: r for r in inputs.get("requirements") or []}
    req_ids = section.get("requirement_ids") or []
    evidence_ids = section.get("evidence_ids") or []
    return bool(
        str(section.get("text") or "").strip()
        and "[검증필요]" not in section["text"]
        and not any(not r.get("verified") for r in section.get("web_references") or [])
        and req_ids
        and evidence_ids
        and all(
            key in requirements
            and requirement_valid(requirements[key], documents)
            and (
                not requirements[key].get("mandatory", True)
                or requirements[key].get("compliance", "unassessed") == "meets"
            )
            for key in req_ids
        )
        and all(
            key in documents
            and documents[key].get("confirmed")
            and not document_issue(documents[key], inputs.get("company") or {})
            and documents[key].get("role") in {"company_evidence", "product_evidence"}
            and str(documents[key].get("text") or "").strip()
            for key in evidence_ids
        )
        and all(requirements[key].get("evidence_id") in evidence_ids for key in req_ids)
    )


def proposal_coverage(inputs: dict) -> dict[str, Any]:
    documents = {d["id"]: d for d in inputs.get("documents") or []}
    sections = [s for s in inputs.get("proposal_sections") or []
                if s.get("document_kind", "qualitative_proposal") == "qualitative_proposal"]
    covered = {
        key
        for section in sections
        if section.get("review_status") == "approved" and section_valid(section, inputs)
        for key in section.get("requirement_ids") or []
    }
    mandatory = [r for r in inputs.get("requirements") or [] if r.get("mandatory")]
    exempt = {
        r["id"]
        for r in mandatory
        if r.get("proposal_disposition") == "evidence_only"
        and str(r.get("proposal_note") or "").strip()
        and requirement_valid(r, documents)
        and r.get("compliance", "unassessed") == "meets"
    }
    return {
        "mandatory_count": len(mandatory),
        "covered_count": sum(r["id"] in covered and r["id"] not in exempt for r in mandatory),
        "evidence_only_count": len(exempt),
        "missing_ids": [r["id"] for r in mandatory if r["id"] not in covered | exempt],
    }


def invalidate_document_dependents(previous: dict, inputs: dict) -> None:
    keys = ("text", "sha256", "role", "confirmed", "item_id")
    before = {d["id"]: {key: d.get(key) for key in keys} for d in previous.get("documents") or []}
    after = {d["id"]: {key: d.get(key) for key in keys} for d in inputs.get("documents") or []}
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    if not changed:
        return
    affected = set()
    if any((before.get(key) or {}).get("role") == "notice_source" or (after.get(key) or {}).get("role") == "notice_source" for key in changed):
        inputs["source_reviewed"] = False
    for requirement in inputs.get("requirements") or []:
        if changed.intersection({requirement.get("document_id"), requirement.get("evidence_id")}):
            affected.add(requirement["id"])
            inputs["source_reviewed"] = False
            requirement["compliance"] = "unassessed"
            if requirement.get("review_status") != "rejected":
                requirement["review_status"] = "pending"
    for section in inputs.get("proposal_sections") or []:
        linked_documents = set(section.get("evidence_ids") or [])
        linked_documents.add((section.get("reference") or {}).get("document_id"))
        linked_documents.update(r.get("document_id") for r in section.get("references") or [])
        linked_requirements = set(section.get("requirement_ids") or [])
        if section.get("review_status") != "rejected" and (changed & linked_documents or affected & linked_requirements):
            section["review_status"] = "pending"
