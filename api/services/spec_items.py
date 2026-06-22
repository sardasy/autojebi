from __future__ import annotations

from typing import Any

PROTECTED_STATUSES = {"reviewed", "matched"}
HWP_STATUSES = {"candidate", "reviewed", "matched"}
LOW_CONFIDENCE_THRESHOLD = 0.75

SPEC_FIELDS: list[dict[str, str]] = [
    {"key": "product_category", "label": "품목", "unit": "", "category": "general"},
    {"key": "quantity", "label": "수량", "unit": "대/식", "category": "general"},
    {"key": "rated_voltage_kv", "label": "정격전압", "unit": "kV", "category": "electrical"},
    {"key": "rated_current_a", "label": "정격전류", "unit": "A", "category": "electrical"},
    {"key": "rated_power_kva", "label": "정격용량", "unit": "kVA", "category": "electrical"},
    {"key": "rated_power_kw", "label": "정격출력", "unit": "kW", "category": "electrical"},
    {"key": "frequency_hz", "label": "주파수", "unit": "Hz", "category": "electrical"},
    {"key": "phases", "label": "상수", "unit": "상", "category": "electrical"},
    {"key": "breaking_capacity_ka", "label": "차단용량", "unit": "kA", "category": "electrical"},
    {"key": "installation_type", "label": "설치방식", "unit": "", "category": "environment"},
    {"key": "cooling_type", "label": "냉각방식", "unit": "", "category": "environment"},
    {"key": "protection_class", "label": "보호등급", "unit": "", "category": "environment"},
    {"key": "standards", "label": "적용규격", "unit": "", "category": "standard"},
    {"key": "delivery_condition", "label": "납품조건", "unit": "", "category": "delivery"},
    {"key": "notes", "label": "기타 요구사항", "unit": "", "category": "other"},
]


def build_spec_item_candidates(row: Any) -> list[dict[str, Any]]:
    analysis = dict(row["analysis"] or {})
    raw = dict(row["raw"] or {})
    elec_spec = dict(analysis.get("elec_spec") or {})
    document_automation = analysis.get("document_automation")
    uploads = []
    if isinstance(document_automation, dict):
        uploads = [u for u in document_automation.get("uploads") or [] if isinstance(u, dict)]

    excerpt = _excerpt(raw, uploads)
    candidates: list[dict[str, Any]] = []
    for sort_order, spec in enumerate(SPEC_FIELDS, start=10):
        key = spec["key"]
        raw_value = _raw_spec_value(key, elec_spec, raw, uploads)
        value_text = _value_to_text(raw_value)
        confidence = 0.85 if value_text else 0.35
        source_file = _first_upload_name(uploads)
        source_text = _source_text(key, value_text, raw, uploads, elec_spec)
        candidates.append(
            {
                "item_key": key,
                "label": spec["label"],
                "required_value": value_text,
                "proposed_value": "",
                "unit": spec["unit"] or None,
                "category": spec["category"],
                "source": "analysis.elec_spec" if value_text else "rule",
                "confidence": confidence,
                "evidence": {
                    "excerpt": _compact(source_text or excerpt or value_text, 300),
                    "file_name": source_file,
                    "method": "rule",
                },
                "status": "candidate",
                "sort_order": sort_order,
                "source_text": _compact(source_text, 1000) if source_text else None,
                "source_file_name": source_file,
                "source_page": None,
                "review_priority": "high" if confidence < LOW_CONFIDENCE_THRESHOLD else "normal",
            }
        )
    return candidates


def merge_candidate_with_existing(
    candidate: dict[str, Any],
    existing: dict[str, Any] | None,
) -> dict[str, Any]:
    if not existing:
        return candidate
    merged = dict(candidate)
    locked_fields = existing.get("locked_fields")
    if not isinstance(locked_fields, list):
        locked_fields = []
    for key in locked_fields:
        if isinstance(key, str) and key in existing:
            merged[key] = existing[key]
    if str(existing.get("status") or "") in PROTECTED_STATUSES:
        for key in (
            "proposed_value",
            "status",
            "note",
            "reviewed_by",
            "reviewed_at",
            "locked_fields",
            "source_text",
            "source_file_name",
            "source_page",
            "review_priority",
        ):
            if key in existing:
                merged[key] = existing[key]
    for key in ("id", "created_at", "updated_at"):
        if key in existing:
            merged[key] = existing[key]
    return merged


def rows_to_technical_compliance_draft(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lines = [
        "| 항목 | 공고 요구사양 | 제안/대응 사양 | 단위 | 확인상태 | 근거 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row.get("status") not in HWP_STATUSES:
            continue
        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        lines.append(
            "| "
            + " | ".join(
                _escape_md_cell(str(value or ""))
                for value in (
                    row.get("label"),
                    row.get("required_value") or "공고문 확인",
                    row.get("proposed_value") or "-",
                    row.get("unit") or "",
                    row.get("status") or "candidate",
                    evidence.get("excerpt") or evidence.get("method") or "",
                )
            )
            + " |"
        )
    return {
        "kind": "markdown",
        "label": "규격대응표 초안",
        "content": "\n".join(lines),
        "source": "notice_spec_items",
    }


def spec_items_summary(rows: list[dict[str, Any]], *, limit: int = 800) -> str:
    parts: list[str] = []
    for row in rows:
        if row.get("status") == "ignored":
            continue
        value = row.get("proposed_value") or row.get("required_value")
        if not value:
            continue
        unit = f" {row.get('unit')}" if row.get("unit") else ""
        parts.append(f"{row.get('label')}: {value}{unit}")
    return _compact("; ".join(parts), limit)


def spec_items_to_elec_spec(rows: list[dict[str, Any]], existing: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(existing or {})
    for row in rows:
        key = str(row.get("item_key") or "")
        if key not in {item["key"] for item in SPEC_FIELDS}:
            continue
        value = row.get("required_value")
        if value in (None, ""):
            continue
        if key in {"quantity", "phases"}:
            updated[key] = _to_int(value)
        elif key in {
            "rated_voltage_kv",
            "rated_current_a",
            "rated_power_kva",
            "rated_power_kw",
            "frequency_hz",
            "breaking_capacity_ka",
        }:
            updated[key] = _to_float(value)
        elif key == "standards":
            updated[key] = [part.strip() for part in str(value).split(",") if part.strip()]
        elif key == "delivery_condition":
            updated.setdefault("notes", str(value))
        else:
            updated[key] = value
    return {k: v for k, v in updated.items() if v not in (None, "", [])}


def compose_hwp_values(row: Any, rows: list[dict[str, Any]], overrides: dict[str, str]) -> dict[str, str]:
    raw = dict(row["raw"] or {})
    values = {
        "notice_no": str(row["notice_no"] or ""),
        "title": str(row["title"] or ""),
        "org_name": str(row.get("org_name") or raw.get("ntceInsttNm") or raw.get("dminsttNm") or ""),
        "product_category": _first_item_value(rows, "product_category"),
        "quantity": _first_item_value(rows, "quantity"),
        "spec_summary": spec_items_summary(rows, limit=500),
        "technical_compliance_summary": spec_items_summary(rows, limit=1000),
    }
    values.update({key: str(value) for key, value in overrides.items()})
    return values


def _raw_spec_value(key: str, elec_spec: dict[str, Any], raw: dict[str, Any], uploads: list[dict[str, Any]]) -> Any:
    if key in elec_spec:
        return elec_spec[key]
    if key == "delivery_condition":
        for raw_key in ("dlvrTmlmtDt", "dlvrDaynum", "delivery_condition"):
            if raw.get(raw_key):
                return raw[raw_key]
    if key == "notes":
        summaries = [
            str(u.get("analysis_summary") or "")
            for u in uploads
            if u.get("analysis_summary")
        ]
        return "\n".join(summaries) or elec_spec.get("notes")
    return None


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _excerpt(raw: dict[str, Any], uploads: list[dict[str, Any]]) -> str:
    for item in uploads:
        summary = str(item.get("analysis_summary") or "").strip()
        if summary:
            return summary
    for key in ("bidNtceNm", "ntceSpecFileNm1", "cntrctCnclsMthdNm", "dminsttNm", "ntceInsttNm"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def _first_upload_name(uploads: list[dict[str, Any]]) -> str | None:
    for item in uploads:
        name = str(item.get("name") or "").strip()
        if name:
            return name
    return None


def _source_text(
    key: str,
    value_text: str,
    raw: dict[str, Any],
    uploads: list[dict[str, Any]],
    elec_spec: dict[str, Any],
) -> str:
    snippets: list[str] = []
    if value_text:
        snippets.append(f"{key}: {value_text}")
    for item in uploads:
        summary = str(item.get("analysis_summary") or "").strip()
        if summary:
            snippets.append(summary)
        error = str(item.get("text_extract_error") or "").strip()
        if error:
            snippets.append(f"extract_error: {error}")
    for raw_key in ("bidNtceNm", "prdctSpecNm", "ntceSpecFileNm1", "cntrctCnclsMthdNm"):
        value = str(raw.get(raw_key) or "").strip()
        if value:
            snippets.append(f"{raw_key}: {value}")
    if not snippets and elec_spec:
        snippets.append(str(elec_spec))
    return "\n".join(snippets)


def _first_item_value(rows: list[dict[str, Any]], item_key: str) -> str:
    for row in rows:
        if row.get("item_key") == item_key:
            return str(row.get("proposed_value") or row.get("required_value") or "")
    return ""


def _escape_md_cell(value: str) -> str:
    return " ".join(value.replace("|", "/").split())


def _compact(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None
