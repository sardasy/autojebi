"""notices 라우터 패키지 공용 헬퍼 — 둘 이상의 서브모듈이 공유하는 함수만 둔다."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update

from api.models.notices import NoticeRecord
from api.services.document_automation import analyze_document_requirements
from api.services.hwp_agent_client import HwpAgentClient
from api.services.spec_items import (
    rows_to_technical_compliance_draft,
    spec_items_summary,
)
from api.tables import (
    bid_pipeline,
    company_profiles,
    notice_errors,
    notice_exports,
    notice_required_documents,
    notice_spec_items,
)


def _row_to_record(row: Any) -> NoticeRecord:
    return NoticeRecord(
        notice_no=row["notice_no"],
        title=row["title"],
        source=row["source"],
        raw=row["raw"],
        category=row["category"],
        fit_score=row["fit_score"],
        assignee=row["assignee"],
        analysis=row["analysis"] or {},
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        bid_no=row.get("bid_no"),
        bid_seq=row.get("bid_seq"),
        bid_type=row.get("bid_type"),
        org_code=row.get("org_code"),
        org_name=row.get("org_name"),
        base_price=_to_float(row.get("base_price")),
        open_date=row.get("open_date"),
        close_date=row.get("close_date"),
        collected_at=row.get("collected_at"),
        score_spec=_to_float(row.get("score_spec")),
        score_qual=_to_float(row.get("score_qual")),
        score_price=_to_float(row.get("score_price")),
        score_total=_to_float(row.get("score_total")),
        grade_reason=row.get("grade_reason"),
        risk_note=row.get("risk_note"),
        top_sku=row.get("top_sku"),
        top_sku_name=row.get("top_sku_name"),
        sku_match_score=_to_float(row.get("sku_match_score")),
        graded_at=row.get("graded_at"),
        unresolved_error_count=int(row.get("unresolved_error_count") or 0),
        export_count=int(row.get("export_count") or 0),
        spec_item_count=int(row.get("spec_item_count") or 0),
    )


def _notice_select_columns() -> list[Any]:
    return [
        *bid_pipeline.c,
        (
            select(func.count())
            .select_from(notice_errors)
            .where(
                notice_errors.c.notice_no == bid_pipeline.c.notice_no,
                notice_errors.c.resolved_at.is_(None),
            )
            .scalar_subquery()
            .label("unresolved_error_count")
        ),
        (
            select(func.count())
            .select_from(notice_exports)
            .where(
                notice_exports.c.notice_no == bid_pipeline.c.notice_no,
                notice_exports.c.deleted_at.is_(None),
            )
            .scalar_subquery()
            .label("export_count")
        ),
        (
            select(func.count())
            .select_from(notice_spec_items)
            .where(notice_spec_items.c.notice_no == bid_pipeline.c.notice_no)
            .scalar_subquery()
            .label("spec_item_count")
        ),
    ]


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _list_spec_item_rows(conn, notice_no: str, *, include_ignored: bool = True) -> list[dict[str, Any]]:
    stmt = (
        select(notice_spec_items)
        .where(notice_spec_items.c.notice_no == notice_no)
        .order_by(notice_spec_items.c.sort_order, notice_spec_items.c.id)
    )
    if not include_ignored:
        stmt = stmt.where(notice_spec_items.c.status != "ignored")
    return [dict(row) for row in conn.execute(stmt).mappings().all()]


def _replace_technical_draft_from_spec_items(document_automation: dict, rows: list[dict[str, Any]]) -> dict:
    updated = dict(document_automation)
    drafts = dict(updated.get("drafts") or {})
    drafts["technical_compliance"] = rows_to_technical_compliance_draft(rows)
    if isinstance(drafts.get("bid_form_values"), dict):
        bid_values = dict(drafts["bid_form_values"])
        values = dict(bid_values.get("values") or {})
        values["technical_compliance_summary"] = spec_items_summary(rows)
        values["spec_summary"] = spec_items_summary(rows, limit=500)
        bid_values["values"] = values
        drafts["bid_form_values"] = bid_values
    updated["drafts"] = drafts
    return updated


# Indirection so tests can monkeypatch this factory without touching env vars.
def _make_hwp_agent_client() -> HwpAgentClient:
    return HwpAgentClient()


def _company_defaults(row: Any) -> dict[str, str]:
    """Standard placeholder values derived from env + the bid_pipeline row.

    Company info comes from env (constant for 미림씨스콘). Notice-specific
    fields come from the row. Caller can override any key in the request body.
    """
    return {
        "company_name": os.getenv("COMPANY_NAME", "").strip(),
        "business_number": os.getenv("COMPANY_BUSINESS_NUMBER", "").strip(),
        "ceo_name": os.getenv("COMPANY_CEO_NAME", "").strip(),
        "address": os.getenv("COMPANY_ADDRESS", "").strip(),
        "notice_no": str(row["notice_no"] or ""),
        "title": str(row["title"] or ""),
        "category": str(row["category"] or ""),
        "assignee": str(row["assignee"] or ""),
        "fit_score": str(row["fit_score"] or 0),
    }


_STAGE_ORDER = {
    "bid": 0, "proposal": 1, "price": 2, "conditional": 3,
    "post_award": 4, "contract": 5, "delivery": 6,
}


def _list_required_document_rows(conn, notice_no: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        select(notice_required_documents).where(
            notice_required_documents.c.notice_no == notice_no
        )
    ).mappings().all()
    return sorted(
        (dict(r) for r in rows),
        key=lambda r: (_STAGE_ORDER.get(r.get("submit_stage"), 9), -float(r.get("confidence") or 0)),
    )


def _load_document_automation(conn, notice_no: str) -> tuple[Any, dict, dict]:
    row = conn.execute(
        select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="notice not found")
    analysis = dict(row["analysis"] or {})
    document_automation = analysis.get("document_automation")
    if not isinstance(document_automation, dict):
        raise HTTPException(
            status_code=409, detail="document automation has not been analyzed"
        )
    return row, analysis, document_automation


def _persist_document_automation(conn, notice_no: str, analysis: dict, document_automation: dict) -> None:
    analysis["document_automation"] = document_automation
    conn.execute(
        update(bid_pipeline)
        .where(bid_pipeline.c.notice_no == notice_no)
        .values(analysis=analysis)
    )


def _record_export(conn, notice_no: str, export: Any, *, created_by: str = "system") -> Any:
    data = export.model_dump() if hasattr(export, "model_dump") else dict(export)
    now = datetime.now(tz=UTC)
    conn.execute(
        update(notice_exports)
        .where(
            notice_exports.c.notice_no == notice_no,
            notice_exports.c.kind == data.get("kind"),
            notice_exports.c.draft_id == data.get("draft_id"),
            notice_exports.c.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    result = conn.execute(
        notice_exports.insert().values(
            notice_no=notice_no,
            kind=str(data.get("kind") or ""),
            draft_id=str(data.get("draft_id") or ""),
            output_path=str(data.get("output_path") or ""),
            mime=str(data.get("mime") or "application/octet-stream"),
            notes=data.get("notes"),
            version=data.get("version"),
            template_version=data.get("template_version"),
            validation_status=str(data.get("validation_status") or "passed"),
            validation_errors=data.get("validation_errors") or [],
            file_size=data.get("file_size"),
            sha256=data.get("sha256"),
            created_at=_parse_dt(data.get("generated_at")) or now,
            created_by=created_by,
        )
    )
    export_id = int(result.inserted_primary_key[0])
    return export.model_copy(update={"id": export_id}) if hasattr(export, "model_copy") else data | {"id": export_id}


def _fallback_company(row: Any) -> dict[str, Any]:
    defaults = _company_defaults(row)
    return {
        "profile_key": "env",
        "company_name": defaults["company_name"],
        "business_number": defaults["business_number"],
        "ceo_name": defaults["ceo_name"],
        "address": defaults["address"],
        "profile_metadata": {},
    }


def _load_company_profile(conn, row: Any) -> dict[str, Any]:
    company = conn.execute(
        select(company_profiles)
        .where(company_profiles.c.active.is_(True))
        .order_by(company_profiles.c.id)
        .limit(1)
    ).mappings().first()
    return dict(company) if company else _fallback_company(row)


def _record_errors(conn, notice_no: str, errors: list[dict[str, Any]]) -> None:
    for item in errors:
        if not isinstance(item, dict):
            continue
        detail = str(item.get("detail") or item.get("message") or "").strip()
        if not detail:
            continue
        conn.execute(
            notice_errors.insert().values(
                notice_no=notice_no,
                stage=str(item.get("stage") or "unknown"),
                severity=str(item.get("severity") or "error"),
                source=str(item.get("source") or "system"),
                file_name=item.get("file_name") or item.get("name"),
                detail=detail,
                raw=item,
            )
        )


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_or_create_document_automation(conn, notice_no: str) -> tuple[Any, dict, dict]:
    row = conn.execute(
        select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="notice not found")
    analysis = dict(row["analysis"] or {})
    document_automation = analysis.get("document_automation")
    if isinstance(document_automation, dict):
        return row, analysis, document_automation
    document_automation = analyze_document_requirements(row)
    analysis["document_automation"] = document_automation
    return row, analysis, document_automation
