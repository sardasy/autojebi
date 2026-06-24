from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

ALLOWED_TRANSFORMS = {
    "none",
    "date_yyyy_mm_dd",
    "number_comma",
    "business_number_dash",
    "strip",
    "truncate_1000",
}


@dataclass(frozen=True)
class ResolvedHwpFields:
    context: dict[str, Any]
    input_values: dict[str, str]
    required_missing: list[str]


def build_hwp_context(
    *,
    row: Any,
    company: dict[str, Any],
    spec_rows: list[dict[str, Any]],
    document_automation: dict[str, Any],
    proposal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = dict(row["raw"] or {})
    analysis = dict(row["analysis"] or {})
    return {
        "company": {
            "profile_key": str(company.get("profile_key") or "default"),
            "company_name": str(company.get("company_name") or ""),
            "business_number": str(company.get("business_number") or ""),
            "ceo_name": str(company.get("ceo_name") or ""),
            "address": str(company.get("address") or ""),
            "profile_metadata": company.get("profile_metadata") or {},
        },
        "notice": {
            "notice_no": str(row["notice_no"] or ""),
            "title": str(row["title"] or ""),
            "source": str(row["source"] or ""),
            "category": str(row["category"] or ""),
            "assignee": str(row["assignee"] or ""),
            "org_name": str(row.get("org_name") or raw.get("ntceInsttNm") or raw.get("dminsttNm") or ""),
            "base_price": row.get("base_price") or raw.get("presmptPrce") or "",
            "open_date": row.get("open_date") or raw.get("bidBeginDt") or "",
            "close_date": row.get("close_date") or raw.get("bidClseDt") or "",
            "raw": raw,
        },
        "grading": {
            "fit_score": row.get("fit_score"),
            "score_spec": row.get("score_spec"),
            "score_qual": row.get("score_qual"),
            "score_price": row.get("score_price"),
            "score_total": row.get("score_total"),
            "grade_reason": row.get("grade_reason"),
            "risk_note": row.get("risk_note"),
            "top_sku": row.get("top_sku"),
            "top_sku_name": row.get("top_sku_name"),
            "sku_match_score": row.get("sku_match_score"),
        },
        "spec_items": spec_rows,
        "document_automation": document_automation,
        "proposal": proposal or {},
        "analysis": analysis,
    }


def resolve_hwp_fields(
    *,
    context: dict[str, Any],
    mappings: list[dict[str, Any]],
    values_override: dict[str, str] | None = None,
) -> ResolvedHwpFields:
    overrides = values_override or {}
    values: dict[str, str] = {}
    required_missing: list[str] = []

    for mapping in mappings:
        field_name = str(mapping.get("hwp_field_name") or "").strip()
        if not field_name:
            continue
        transform = str(mapping.get("transform") or "none")
        if transform not in ALLOWED_TRANSFORMS:
            raise ValueError(f"unsupported transform: {transform}")

        if field_name in overrides:
            raw_value: Any = overrides[field_name]
        else:
            raw_value = _get_path(context, str(mapping.get("context_path") or ""))
            if raw_value in (None, ""):
                raw_value = mapping.get("default_value")

        rendered = _apply_transform(raw_value, transform)
        if bool(mapping.get("required")) and not rendered:
            required_missing.append(field_name)
        values[field_name] = rendered

    return ResolvedHwpFields(
        context=context,
        input_values=values,
        required_missing=required_missing,
    )


def _get_path(data: Any, path: str) -> Any:
    if not path:
        return None
    current = data
    for part in path.split("."):
        if not part:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _apply_transform(value: Any, transform: str) -> str:
    if value is None:
        text = ""
    elif isinstance(value, datetime):
        text = value.date().isoformat()
    elif isinstance(value, date):
        text = value.isoformat()
    elif isinstance(value, list | tuple):
        text = ", ".join(str(item) for item in value if item not in (None, ""))
    else:
        text = str(value)

    if transform == "none":
        return text
    if transform == "strip":
        return text.strip()
    if transform == "truncate_1000":
        return text.strip()[:1000]
    if transform == "date_yyyy_mm_dd":
        return _format_date(text)
    if transform == "number_comma":
        return _format_number(text)
    if transform == "business_number_dash":
        return _format_business_number(text)
    raise ValueError(f"unsupported transform: {transform}")


def _format_date(text: str) -> str:
    value = text.strip()
    if not value:
        return ""
    normalized = value.replace(".", "-").replace("/", "-")
    if "T" in normalized:
        normalized = normalized.split("T", 1)[0]
    if " " in normalized:
        normalized = normalized.split(" ", 1)[0]
    compact = normalized.replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return value


def _format_number(text: str) -> str:
    value = text.strip().replace(",", "")
    if not value:
        return ""
    try:
        number = Decimal(value)
    except InvalidOperation:
        return text.strip()
    if number == number.to_integral():
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _format_business_number(text: str) -> str:
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 10:
        return text.strip()
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
