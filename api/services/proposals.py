from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.models.notices import ExportRecord
from api.services.exporters import HWP_MIME, notice_dir, with_file_metadata
from api.services.spec_items import spec_items_summary

PROPOSAL_PLACEHOLDERS = [
    "notice_no",
    "title",
    "org_name",
    "product_category",
    "spec_summary",
    "technical_compliance_summary",
    "top_sku_name",
    "company_name",
]


def build_proposal_payload(
    *,
    row: Any,
    spec_rows: list[dict[str, Any]],
    document_automation: dict[str, Any],
    company_values: dict[str, str],
    overrides: dict[str, str],
) -> dict[str, Any]:
    raw = dict(row["raw"] or {})
    uploads = [
        item
        for item in document_automation.get("uploads") or []
        if isinstance(item, dict)
    ]
    included = [item for item in spec_rows if item.get("status") in {"candidate", "reviewed", "matched"}]
    risks = list(document_automation.get("risks") or [])
    risks.extend(
        f"{item.get('label')}: {item.get('required_value') or '-'}"
        for item in spec_rows
        if item.get("status") in {"gap", "ignored"}
    )

    values = {
        **company_values,
        "notice_no": str(row["notice_no"] or ""),
        "title": str(row["title"] or ""),
        "org_name": str(row.get("org_name") or raw.get("ntceInsttNm") or raw.get("dminsttNm") or ""),
        "product_category": _first_spec_value(included, "product_category") or str(row["category"] or ""),
        "spec_summary": spec_items_summary(included, limit=700),
        "technical_compliance_summary": spec_items_summary(included, limit=1200),
        "top_sku_name": str(row.get("top_sku_name") or row.get("top_sku") or ""),
        "base_price": str(row.get("base_price") or raw.get("presmptPrce") or ""),
        "close_date": str(row.get("close_date") or raw.get("bidClseDt") or ""),
        "upload_summary": _upload_summary(uploads),
    }
    values.update({key: str(value) for key, value in overrides.items()})

    sections = [
        {"title": "회사 소개", "content": _company_intro(values)},
        {"title": "공고 개요", "content": _notice_overview(values)},
        {"title": "제안 품목", "content": _product_summary(values)},
        {"title": "규격 대응 요약", "content": values["technical_compliance_summary"] or "규격 항목 검토 필요"},
        {"title": "납품/지원 방안", "content": _delivery_summary(included, values)},
        {"title": "리스크/확인사항", "content": "\n".join(risks) or "특이 리스크 없음"},
    ]
    tables = [
        {
            "title": "규격 대응표",
            "headers": ["항목", "요구사양", "제안/대응", "상태"],
            "rows": [
                [
                    str(item.get("label") or ""),
                    str(item.get("required_value") or ""),
                    str(item.get("proposed_value") or ""),
                    str(item.get("status") or ""),
                ]
                for item in included
            ],
        }
    ]
    return {
        "kind": "hwp_proposal",
        "label": "제안서 HWP 초안",
        "values": values,
        "sections": sections,
        "tables": tables,
        "required_placeholders": PROPOSAL_PLACEHOLDERS,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source": "notice+document_automation+notice_spec_items",
    }


def build_proposal_export(*, notice_no: str, output_path: str, notes: str | None = None) -> ExportRecord:
    return with_file_metadata(
        ExportRecord(
            kind="proposal_hwp",
            draft_id="proposal",
            output_path=output_path,
            mime=HWP_MIME,
            generated_at=datetime.now(tz=UTC).isoformat(),
            notes=notes,
            version="proposal_hwp_v1",
            template_version="proposal_compose_v1",
            validation_status="passed",
        )
    )


def proposal_output_path(notice_no: str) -> str:
    return str(notice_dir(notice_no) / f"proposal_{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}.hwp")


def _first_spec_value(rows: list[dict[str, Any]], item_key: str) -> str:
    for row in rows:
        if row.get("item_key") == item_key:
            return str(row.get("proposed_value") or row.get("required_value") or "")
    return ""


def _upload_summary(uploads: list[dict[str, Any]]) -> str:
    parts = [
        f"{item.get('name')}: {item.get('analysis_summary')}"
        for item in uploads
        if item.get("analysis_summary")
    ]
    return "\n".join(parts[:5])


def _company_intro(values: dict[str, str]) -> str:
    company = values.get("company_name") or "제안사"
    return f"{company}는 공고 요구사항에 맞춰 전력전자/전력기기 공급 및 기술 지원을 수행합니다."


def _notice_overview(values: dict[str, str]) -> str:
    return "\n".join(
        part
        for part in (
            f"공고번호: {values.get('notice_no')}",
            f"공고명: {values.get('title')}",
            f"기관: {values.get('org_name')}",
            f"마감일: {values.get('close_date')}",
            f"예가: {values.get('base_price')}",
        )
        if part.split(": ", 1)[-1]
    )


def _product_summary(values: dict[str, str]) -> str:
    parts = [
        f"제안 품목: {values.get('product_category') or '공고 규격 기준'}",
        f"추천 SKU: {values.get('top_sku_name') or '검토 필요'}",
        values.get("spec_summary") or "",
    ]
    return "\n".join(part for part in parts if part)


def _delivery_summary(rows: list[dict[str, Any]], values: dict[str, str]) -> str:
    delivery = _first_spec_value(rows, "delivery_condition")
    if delivery:
        return f"납품 조건: {delivery}\n요구 규격 검토 후 납품 및 기술 지원 일정을 확정합니다."
    return "공고 납품 조건과 담당자 검토 결과에 따라 납품 및 기술 지원 일정을 확정합니다."
