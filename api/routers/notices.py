from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    cast,
    delete,
    func,
    nullslast,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert

from api.auth import verify_api_key
from api.config import settings
from api.db import require_engine
from api.models.notices import (
    AttachmentFetchFileResult,
    AttachmentFetchResponse,
    AutofillFormRequest,
    AutofillFormResponse,
    ChecklistUpdateRequest,
    DocumentAutomationResponse,
    DocumentAutomationResult,
    DocumentValidationResponse,
    E2ECleanupResponse,
    ExportCreateRequest,
    ExportKind,
    ExportResponse,
    GradeRequest,
    HwpComposeBidFormResult,
    HwpComposeRequest,
    HwpComposeResponse,
    MailExtractRequest,
    MailExtractResponse,
    NoticeAnalyzeResponse,
    NoticeGradeResponse,
    NoticeListResponse,
    NoticeRecord,
    NoticeSearchRequest,
    NoticeSearchResponse,
    NoticeSpecItem,
    NoticeSummary,
    NoticeUpsertRequest,
    NotifyRequest,
    NotifyResponse,
    ProposalComposeRequest,
    ProposalComposeResponse,
    ProposalComposeResult,
    SpecItemExtractResponse,
    SpecItemListResponse,
    SpecItemUpdateRequest,
    UploadedDocument,
    UploadListResponse,
    UploadResponse,
)
from api.services.claude_analyzer import ClaudeAnalyzer
from api.services.document_automation import (
    analyze_document_requirements,
    attach_bid_form_result,
    update_checklist_item,
    validate_document_automation,
    validate_pre_compose,
)
from api.services.exporters import (
    build_excel,
    build_hwp,
    get_technical_compliance_draft,
    lookup_export,
    merge_export_into_document_automation,
)
from api.services.g2b_attachments import (
    bytes_stream,
    download_g2b_attachment,
    iter_g2b_attachments,
)
from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError
from api.services.mail_extractor import extract_notice_from_mail
from api.services.notifications import TeamsNotifier
from api.services.proposals import (
    build_proposal_export,
    build_proposal_payload,
    proposal_output_path,
)
from api.services.routing import assignee_for_category
from api.services.spec_items import (
    build_spec_item_candidates,
    compose_hwp_values,
    merge_candidate_with_existing,
    rows_to_technical_compliance_draft,
    spec_items_summary,
    spec_items_to_elec_spec,
)
from api.services.status import advance_status, can_transition, compute_notify_status
from api.services.uploads import (
    analyze_upload,
    build_metadata,
    clone_common_upload_for_notice,
    delete_file,
    get_common_upload,
    merge_into_document_automation,
    remove_from_document_automation,
    save_stream,
)

router = APIRouter(
    prefix="/notices",
    tags=["notices"],
    dependencies=[Depends(verify_api_key)],
)

metadata = MetaData()

bid_pipeline = Table(
    "bid_pipeline",
    metadata,
    Column("notice_no", String, primary_key=True),
    Column("title", String),
    Column("source", String),
    Column("raw", JSON),
    Column("category", String),
    Column("fit_score", Integer),
    Column("assignee", String),
    Column("analysis", JSON),
    Column("status", String),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    # G2B 수집 컬럼 (db/migrations/0001_collect_columns.sql)
    Column("bid_no", String),
    Column("bid_seq", String),
    Column("bid_type", String),
    Column("org_code", String),
    Column("org_name", String),
    Column("base_price", Numeric(18, 2)),
    Column("open_date", DateTime(timezone=True)),
    Column("close_date", DateTime(timezone=True)),
    Column("collected_at", DateTime(timezone=True)),
    # M3 그레이딩 컬럼 (db/migrations/0002_grade_columns.sql)
    Column("score_spec", Numeric(4, 3)),
    Column("score_qual", Numeric(4, 3)),
    Column("score_price", Numeric(4, 3)),
    Column("score_total", Numeric(4, 3)),
    Column("grade_reason", String),
    Column("risk_note", String),
    Column("top_sku", String),
    Column("top_sku_name", String),
    Column("sku_match_score", Numeric(4, 3)),
    Column("graded_at", DateTime(timezone=True)),
)

notice_spec_items = Table(
    "notice_spec_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("notice_no", String, ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"), nullable=False),
    Column("item_key", String, nullable=False),
    Column("label", String, nullable=False),
    Column("required_value", Text),
    Column("proposed_value", Text),
    Column("unit", String),
    Column("category", String, nullable=False, default="technical"),
    Column("source", String, nullable=False, default="rule"),
    Column("confidence", Numeric(4, 3), nullable=False, default=0),
    Column("evidence", JSON, nullable=False, default=dict),
    Column("status", String, nullable=False, default="candidate"),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("note", Text),
    Column("reviewed_by", String),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("locked_fields", JSON, nullable=False, default=list),
    Column("source_text", Text),
    Column("source_file_name", String),
    Column("source_page", String),
    Column("review_priority", String, nullable=False, default="normal"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("notice_no", "item_key", name="notice_spec_items_notice_item_unique"),
    CheckConstraint("status IN ('candidate','reviewed','matched','gap','ignored')"),
    CheckConstraint("review_priority IN ('normal','high')"),
    Index("notice_spec_items_notice_idx", "notice_no"),
    Index("notice_spec_items_status_idx", "status"),
)

notice_exports = Table(
    "notice_exports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("notice_no", String, ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"), nullable=False),
    Column("kind", String, nullable=False),
    Column("draft_id", String, nullable=False),
    Column("output_path", Text, nullable=False),
    Column("mime", String, nullable=False),
    Column("notes", Text),
    Column("version", String),
    Column("template_version", String),
    Column("validation_status", String, nullable=False, default="passed"),
    Column("validation_errors", JSON, nullable=False, default=list),
    Column("file_size", Integer),
    Column("sha256", String),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("created_by", String),
    Column("deleted_at", DateTime(timezone=True)),
    CheckConstraint("kind IN ('excel','hwp','proposal_hwp')"),
    CheckConstraint("validation_status IN ('passed','warning','failed')"),
    Index("notice_exports_notice_idx", "notice_no"),
    Index("notice_exports_active_idx", "notice_no", "kind", "draft_id", "deleted_at"),
)

notice_errors = Table(
    "notice_errors",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("notice_no", String, ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"), nullable=False),
    Column("stage", String, nullable=False),
    Column("severity", String, nullable=False, default="error"),
    Column("source", String, nullable=False, default="system"),
    Column("file_name", String),
    Column("detail", Text, nullable=False),
    Column("raw", JSON, nullable=False, default=dict),
    Column("resolved_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("severity IN ('info','warning','error')"),
    Index("notice_errors_notice_idx", "notice_no"),
    Index("notice_errors_unresolved_idx", "notice_no", "resolved_at"),
)

attachment_fetch_jobs = Table(
    "attachment_fetch_jobs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("notice_no", String, ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"), nullable=False),
    Column("status", String, nullable=False, default="pending"),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True)),
    Column("created_by", String),
    CheckConstraint("status IN ('pending','running','completed','completed_with_errors')"),
    Index("attachment_fetch_jobs_notice_idx", "notice_no"),
)

attachment_fetch_files = Table(
    "attachment_fetch_files",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_id", Integer, ForeignKey("attachment_fetch_jobs.id", ondelete="CASCADE"), nullable=False),
    Column("notice_no", String, ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"), nullable=False),
    Column("filename", String, nullable=False),
    Column("url", Text, nullable=False),
    Column("status", String, nullable=False, default="pending"),
    Column("upload_id", String),
    Column("error", Text),
    Column("source_ref", String, nullable=False, default="g2b_attachment"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('pending','success','failed','skipped')"),
    Index("attachment_fetch_files_job_idx", "job_id"),
    Index("attachment_fetch_files_notice_idx", "notice_no"),
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


def _spec_item_to_model(row: Any) -> NoticeSpecItem:
    return NoticeSpecItem(
        id=int(row["id"]),
        notice_no=str(row["notice_no"]),
        item_key=str(row["item_key"]),
        label=str(row["label"]),
        required_value=row.get("required_value"),
        proposed_value=row.get("proposed_value"),
        unit=row.get("unit"),
        category=str(row.get("category") or "technical"),
        source=str(row.get("source") or "rule"),
        confidence=float(row.get("confidence") or 0),
        evidence=dict(row.get("evidence") or {}),
        status=row.get("status") or "candidate",
        sort_order=int(row.get("sort_order") or 0),
        note=row.get("note"),
        reviewed_by=row.get("reviewed_by"),
        reviewed_at=row.get("reviewed_at"),
        locked_fields=list(row.get("locked_fields") or []),
        source_text=row.get("source_text"),
        source_file_name=row.get("source_file_name"),
        source_page=row.get("source_page"),
        review_priority=row.get("review_priority") or "normal",
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


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


@router.post("/extract-from-mail", response_model=MailExtractResponse)
def extract_from_mail(payload: MailExtractRequest) -> MailExtractResponse:
    """M12 — KJEBI 알림메일 paste → Claude tool-use 추출 → notice_no 있으면 upsert.

    실 메일 샘플이 확보되기 전까지의 1차 운영 경로. n8n 자동화는 M12.5에서 본격 구현.
    notice_no 추출 실패 시 upserted=null로 반환 — 호출자(프론트)가 사용자에게 경고.
    """
    result = extract_notice_from_mail(payload.raw_text)
    upserted: NoticeRecord | None = None

    if result.extracted.notice_no:
        upsert_payload = NoticeUpsertRequest(
            notice_no=result.extracted.notice_no,
            title=result.extracted.title,
            source=payload.source,
            raw={
                "kjebi_mail": payload.raw_text,
                "extracted": result.extracted.model_dump(),
            },
        )
        upserted = upsert_notice(upsert_payload)

    return MailExtractResponse(
        extracted=result.extracted,
        upserted=upserted,
        confidence=result.confidence,
        errors=result.errors,
    )


@router.post("/search", response_model=NoticeSearchResponse)
def search_notices_endpoint(payload: NoticeSearchRequest) -> NoticeSearchResponse:
    """M13 — G2B 라이브 검색. DB write 없음.

    페이지네이션: payload.page (>=1), payload.page_size (1..200, 기본 50).
    응답은 슬라이스된 items + 전체 total/total_pages를 함께 반환한다.
    page > total_pages인 경우도 정상 응답 (빈 items + 정확한 meta).

    422 — 빈 키워드 / start > end / 365일 초과 / page<1 / page_size 범위 위반.
    502 — G2B API 호출 실패 (네트워크/HTTP/파싱).
    """
    from datetime import date as _date
    from datetime import timedelta as _td

    from api.collector.pipeline import search_notices

    keyword = (payload.keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="keyword must not be empty")

    today = _date.today()
    start = payload.start_date.date() if payload.start_date else (today - _td(days=30))
    end = payload.end_date.date() if payload.end_date else (today + _td(days=30))

    if start > end:
        raise HTTPException(
            status_code=422, detail=f"start_date {start} must not be after end_date {end}"
        )
    if (end - start).days > 365:
        raise HTTPException(
            status_code=422, detail="search range must not exceed 365 days"
        )

    engine = require_engine()
    try:
        return search_notices(
            engine=engine,
            start=start,
            end=end,
            keyword=keyword,
            page=payload.page,
            page_size=payload.page_size,
        )
    except HTTPException:
        raise
    except Exception as exc:
        # G2B HTTP/네트워크/파싱 실패 → 외부 의존성 장애로 분류
        raise HTTPException(status_code=502, detail=f"G2B search failed: {exc}")


@router.post("/upsert", response_model=NoticeRecord)
def upsert_notice(payload: NoticeUpsertRequest) -> NoticeRecord:
    engine = require_engine()
    now = datetime.now(tz=UTC)

    stmt = insert(bid_pipeline).values(
        notice_no=payload.notice_no,
        title=payload.title,
        source=payload.source,
        raw=payload.raw,
        category="비관련",
        fit_score=0,
        assignee="미배정",
        analysis={},
        status="collected",
        created_at=now,
        updated_at=now,
    )

    # Idempotency rule:
    # - Never downgrade status; keep existing status on conflict.
    stmt = stmt.on_conflict_do_update(
        index_elements=[bid_pipeline.c.notice_no],
        set_={
            "title": stmt.excluded.title,
            "source": stmt.excluded.source,
            "raw": stmt.excluded.raw,
            "updated_at": now,
            "status": bid_pipeline.c.status,
        },
    ).returning(*bid_pipeline.c)

    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().one()
        return _row_to_record(row)


@router.post("/e2e/cleanup", response_model=E2ECleanupResponse)
def cleanup_e2e_notices() -> E2ECleanupResponse:
    if not settings.e2e_cleanup_enabled:
        raise HTTPException(status_code=403, detail="E2E cleanup is disabled")

    engine = require_engine()
    deleted_files = 0
    with engine.begin() as conn:
        rows = conn.execute(
            select(bid_pipeline.c.notice_no, bid_pipeline.c.analysis).where(
                bid_pipeline.c.notice_no.like("E2E-%")
            )
        ).mappings().all()
        notice_nos = [str(row["notice_no"]) for row in rows]

        for row in rows:
            for path in _e2e_runtime_paths(row["analysis"]):
                if delete_file(path):
                    deleted_files += 1

        if notice_nos:
            conn.execute(
                delete(attachment_fetch_files).where(attachment_fetch_files.c.notice_no.in_(notice_nos))
            )
            conn.execute(
                delete(attachment_fetch_jobs).where(attachment_fetch_jobs.c.notice_no.in_(notice_nos))
            )
            conn.execute(delete(notice_errors).where(notice_errors.c.notice_no.in_(notice_nos)))
            conn.execute(delete(notice_exports).where(notice_exports.c.notice_no.in_(notice_nos)))
            conn.execute(delete(notice_spec_items).where(notice_spec_items.c.notice_no.in_(notice_nos)))
            conn.execute(delete(bid_pipeline).where(bid_pipeline.c.notice_no.in_(notice_nos)))

        return E2ECleanupResponse(deleted_notices=len(notice_nos), deleted_files=deleted_files)


def _e2e_runtime_paths(analysis: Any) -> list[str]:
    docs = (analysis or {}).get("document_automation") if isinstance(analysis, dict) else None
    if not isinstance(docs, dict):
        return []
    paths: list[str] = []
    for item in docs.get("uploads") or []:
        if not isinstance(item, dict) or item.get("source_ref") == "common_library":
            continue
        storage_path = str(item.get("storage_path") or "").strip()
        if storage_path:
            paths.append(storage_path)
    for item in docs.get("exports") or []:
        if not isinstance(item, dict):
            continue
        output_path = str(item.get("output_path") or "").strip()
        if output_path:
            paths.append(output_path)
    return paths


@router.post("/{notice_no}/analyze", response_model=NoticeAnalyzeResponse)
def analyze_notice(notice_no: str) -> NoticeAnalyzeResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*_notice_select_columns()).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")

        current_status = row["status"]
        if not can_transition(current_status, "analyzed"):
            raise HTTPException(status_code=409, detail=f"invalid transition {current_status} -> analyzed")

        analyzer = ClaudeAnalyzer()
        result = analyzer.analyze_notice(notice_no=notice_no, title=row["title"], raw=row["raw"])
        assignee = assignee_for_category(result.category)
        schema_errors = [
            {"stage": "claude.schema", "source": "claude", "detail": str(err)}
            for err in (result.analysis.get("schema_errors") or [])
        ]
        _record_errors(conn, notice_no, schema_errors)

        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(
                category=result.category,
                fit_score=result.fit_score,
                assignee=assignee,
                analysis=result.analysis,
                status="analyzed",
            )
        )

        return NoticeAnalyzeResponse(
            notice_no=notice_no,
            category=result.category,  # type: ignore[arg-type]
            fit_score=result.fit_score,
            assignee=assignee,
            analysis=result.analysis,
            status="analyzed",
        )


@router.post("/{notice_no}/notify", response_model=NotifyResponse)
def notify_notice(notice_no: str, body: NotifyRequest) -> NotifyResponse:
    engine = require_engine()
    notifier = TeamsNotifier()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")

        next_status = compute_notify_status(int(row["fit_score"] or 0))
        if not can_transition(row["status"], next_status):
            raise HTTPException(
                status_code=409, detail=f"invalid transition {row['status']} -> {next_status}"
            )

        title = f"[입찰] {row['title'] or notice_no}"
        body_text = (
            f"- 공고번호: {notice_no}\n"
            f"- 카테고리: {row['category']}\n"
            f"- 적합도: {row['fit_score']}\n"
            f"- 담당자: {row['assignee']}\n"
            f"- 상태: {next_status}\n"
        )
        outcome = notifier.deliver(title=title, body=body_text, dry_run=body.dry_run)

        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(status=next_status)
        )

        return NotifyResponse(notice_no=notice_no, status=next_status, delivered=outcome.delivered)


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


@router.post("/{notice_no}/autofill-form", response_model=AutofillFormResponse)
def autofill_form(notice_no: str, body: AutofillFormRequest) -> AutofillFormResponse:
    """Drives milim-hwp-agent to autofill an HWP bid-form template.

    Transitions analyzed → form_filled. Caller-supplied `values` override
    env-derived company defaults; the agent decides which placeholders are
    still missing and rejects with 422 if any required value is blank.
    """
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")

        if not can_transition(row["status"], "form_filled"):
            raise HTTPException(
                status_code=409,
                detail=f"invalid transition {row['status']} -> form_filled",
            )

        merged_values = {**_company_defaults(row), **body.values}

        client = _make_hwp_agent_client()
        try:
            outcome = client.autofill_bid_form(
                template_path=body.template_path,
                output_path=body.output_path,
                values=merged_values,
                visible=body.visible,
            )
        except HwpAgentError as exc:
            existing = dict(row["analysis"] or {})
            errors = list(existing.get("errors") or [])
            errors.append({"stage": "autofill_form", "detail": str(exc)})
            existing["errors"] = errors
            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=existing)
            )
            raise HTTPException(status_code=502, detail=f"hwp agent failed: {exc}")

        merged_analysis = dict(row["analysis"] or {})
        merged_analysis["bid_form"] = {
            "template_path": outcome.template_path,
            "output_path": outcome.output_path,
            "placeholders": outcome.placeholders,
            "replaced": outcome.replaced,
            "missing": outcome.missing,
            "remaining_placeholders": outcome.remaining_placeholders,
            "filled_at": datetime.now(tz=UTC).isoformat(),
        }
        merged_analysis = attach_bid_form_result(
            merged_analysis,
            template_path=outcome.template_path,
            output_path=outcome.output_path,
            replaced=outcome.replaced,
            missing=outcome.missing,
            remaining_placeholders=outcome.remaining_placeholders,
        )

        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(analysis=merged_analysis, status="form_filled")
        )

        return AutofillFormResponse(
            notice_no=notice_no,
            status="form_filled",
            template_path=outcome.template_path,
            output_path=outcome.output_path,
            replaced=outcome.replaced,
            missing=outcome.missing,
            remaining_placeholders=outcome.remaining_placeholders,
        )


@router.post("/{notice_no}/documents/analyze", response_model=DocumentAutomationResponse)
def analyze_documents(notice_no: str) -> DocumentAutomationResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        if row["status"] not in {
            "analyzed",
            "attachments_fetched",
            "documents_analyzed",
            "spec_extracted",
            "hwp_composed",
            "form_filled",
        }:
            raise HTTPException(
                status_code=409,
                detail=f"documents can be analyzed only after notice analysis (current: {row['status']})",
            )

        merged_analysis = dict(row["analysis"] or {})
        previous_docs = merged_analysis.get("document_automation")
        document_automation = analyze_document_requirements(row)
        new_errors = list(document_automation.get("errors") or [])
        if isinstance(previous_docs, dict):
            for key in ("uploads", "exports"):
                if previous_docs.get(key):
                    document_automation[key] = list(previous_docs.get(key) or [])
            if previous_docs.get("errors"):
                document_automation["errors"] = list(previous_docs.get("errors") or []) + list(
                    document_automation.get("errors") or []
                )
        _record_errors(conn, notice_no, new_errors)
        merged_analysis["document_automation"] = document_automation
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(
                analysis=merged_analysis,
                status=advance_status(row["status"], "documents_analyzed"),
            )
        )
        return DocumentAutomationResponse(
            notice_no=notice_no,
            document_automation=DocumentAutomationResult.model_validate(document_automation),
        )


@router.post("/{notice_no}/spec-items/extract", response_model=SpecItemExtractResponse)
def extract_spec_items(notice_no: str) -> SpecItemExtractResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")

        existing_rows = {
            item["item_key"]: item
            for item in _list_spec_item_rows(conn, notice_no)
            if item.get("item_key")
        }
        upserted = 0
        for candidate in build_spec_item_candidates(row):
            merged = merge_candidate_with_existing(
                candidate,
                existing_rows.get(candidate["item_key"]),
            )
            values = {
                "notice_no": notice_no,
                "item_key": merged["item_key"],
                "label": merged["label"],
                "required_value": merged.get("required_value") or None,
                "proposed_value": merged.get("proposed_value") or None,
                "unit": merged.get("unit") or None,
                "category": merged.get("category") or "technical",
                "source": merged.get("source") or "rule",
                "confidence": merged.get("confidence") or 0,
                "evidence": merged.get("evidence") or {},
                "status": merged.get("status") or "candidate",
                "sort_order": merged.get("sort_order") or 0,
                "note": merged.get("note"),
                "reviewed_by": merged.get("reviewed_by"),
                "reviewed_at": merged.get("reviewed_at"),
                "locked_fields": merged.get("locked_fields") or [],
                "source_text": merged.get("source_text"),
                "source_file_name": merged.get("source_file_name"),
                "source_page": merged.get("source_page"),
                "review_priority": merged.get("review_priority") or "normal",
                "updated_at": datetime.now(tz=UTC),
            }
            if merged.get("id"):
                conn.execute(
                    update(notice_spec_items)
                    .where(notice_spec_items.c.id == merged["id"])
                    .values(**values)
                )
            else:
                conn.execute(notice_spec_items.insert().values(**values))
            upserted += 1

        rows = _list_spec_item_rows(conn, notice_no)
        analysis = dict(row["analysis"] or {})
        analysis["elec_spec"] = spec_items_to_elec_spec(
            rows,
            dict(analysis.get("elec_spec") or {}),
        )
        docs = analysis.get("document_automation")
        if isinstance(docs, dict):
            analysis["document_automation"] = _replace_technical_draft_from_spec_items(docs, rows)
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(
                analysis=analysis,
                status=advance_status(row["status"], "spec_extracted"),
            )
        )

        return SpecItemExtractResponse(
            notice_no=notice_no,
            items=[_spec_item_to_model(item) for item in rows],
            upserted=upserted,
        )


@router.get("/{notice_no}/spec-items", response_model=SpecItemListResponse)
def list_spec_items(notice_no: str) -> SpecItemListResponse:
    engine = require_engine()
    with engine.begin() as conn:
        exists = conn.execute(
            select(bid_pipeline.c.notice_no).where(bid_pipeline.c.notice_no == notice_no)
        ).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="notice not found")
        rows = _list_spec_item_rows(conn, notice_no)
        return SpecItemListResponse(
            notice_no=notice_no,
            items=[_spec_item_to_model(item) for item in rows],
        )


@router.patch("/{notice_no}/spec-items/{item_id}", response_model=NoticeSpecItem)
def patch_spec_item(
    notice_no: str,
    item_id: int,
    body: SpecItemUpdateRequest,
) -> NoticeSpecItem:
    engine = require_engine()
    with engine.begin() as conn:
        current = conn.execute(
            select(notice_spec_items).where(
                notice_spec_items.c.notice_no == notice_no,
                notice_spec_items.c.id == item_id,
            )
        ).mappings().one_or_none()
        if not current:
            raise HTTPException(status_code=404, detail="spec item not found")
        values = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if values:
            now = datetime.now(tz=UTC)
            values["updated_at"] = now
            if "source" not in values:
                values["source"] = "manual"
            next_status = values.get("status") or current.get("status")
            if next_status in {"reviewed", "matched"}:
                values.setdefault("reviewed_by", "manual")
                values.setdefault("reviewed_at", now)
            conn.execute(
                update(notice_spec_items)
                .where(notice_spec_items.c.id == item_id)
                .values(**values)
            )
        updated = conn.execute(
            select(notice_spec_items).where(notice_spec_items.c.id == item_id)
        ).mappings().one()

        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if row:
            rows = _list_spec_item_rows(conn, notice_no)
            analysis = dict(row["analysis"] or {})
            analysis["elec_spec"] = spec_items_to_elec_spec(
                rows,
                dict(analysis.get("elec_spec") or {}),
            )
            docs = analysis.get("document_automation")
            if isinstance(docs, dict):
                analysis["document_automation"] = _replace_technical_draft_from_spec_items(docs, rows)
            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=analysis)
            )
        return _spec_item_to_model(dict(updated))


@router.patch(
    "/{notice_no}/documents/checklist/{item_id}",
    response_model=DocumentAutomationResponse,
)
def patch_document_checklist_item(
    notice_no: str,
    item_id: str,
    body: ChecklistUpdateRequest,
) -> DocumentAutomationResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        analysis = dict(row["analysis"] or {})
        document_automation = analysis.get("document_automation")
        if not isinstance(document_automation, dict):
            raise HTTPException(status_code=409, detail="document automation has not been analyzed")
        try:
            updated_docs = update_checklist_item(
                document_automation,
                item_id,
                status=body.status,
                owner=body.owner,
                note=body.note,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="checklist item not found")

        analysis["document_automation"] = updated_docs
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(analysis=analysis)
        )
        return DocumentAutomationResponse(
            notice_no=notice_no,
            document_automation=DocumentAutomationResult.model_validate(updated_docs),
        )


@router.post("/{notice_no}/documents/validate", response_model=DocumentValidationResponse)
def validate_documents(notice_no: str) -> DocumentValidationResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        analysis = dict(row["analysis"] or {})
        document_automation = analysis.get("document_automation")
        if not isinstance(document_automation, dict):
            raise HTTPException(status_code=409, detail="document automation has not been analyzed")

        updated_docs = validate_document_automation(document_automation)
        analysis["document_automation"] = updated_docs
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(analysis=analysis)
        )
        result = DocumentAutomationResult.model_validate(updated_docs)
        return DocumentValidationResponse(
            notice_no=notice_no,
            ready_for_submission=result.ready_for_submission,
            missing_required=result.missing_required,
            checklist=result.checklist,
        )


# ── M11: 서류 자동화 v2 — 파일 업로드 + Excel/HWP 내보내기 ──


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


def _lookup_active_export(conn, notice_no: str, *, kind: str, draft_id: str) -> dict | None:
    row = conn.execute(
        select(notice_exports)
        .where(
            notice_exports.c.notice_no == notice_no,
            notice_exports.c.kind == kind,
            notice_exports.c.draft_id == draft_id,
            notice_exports.c.deleted_at.is_(None),
        )
        .order_by(notice_exports.c.created_at.desc(), notice_exports.c.id.desc())
        .limit(1)
    ).mappings().first()
    if not row:
        return None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "draft_id": row["draft_id"],
        "output_path": row["output_path"],
        "mime": row["mime"],
        "generated_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
        "notes": row["notes"],
        "version": row["version"],
        "template_version": row["template_version"],
        "validation_status": row["validation_status"],
        "validation_errors": row["validation_errors"] or [],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
    }


def _lookup_export_by_id(conn, notice_no: str, export_id: int) -> dict | None:
    row = conn.execute(
        select(notice_exports)
        .where(
            notice_exports.c.id == export_id,
            notice_exports.c.notice_no == notice_no,
            notice_exports.c.deleted_at.is_(None),
        )
        .limit(1)
    ).mappings().first()
    if not row:
        return None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "draft_id": row["draft_id"],
        "output_path": row["output_path"],
        "mime": row["mime"],
        "generated_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat")
        else row["created_at"],
        "notes": row["notes"],
        "version": row["version"],
        "template_version": row["template_version"],
        "validation_status": row["validation_status"],
        "validation_errors": row["validation_errors"] or [],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
    }


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


def _create_attachment_job(conn, notice_no: str) -> int:
    result = conn.execute(
        attachment_fetch_jobs.insert().values(
            notice_no=notice_no,
            status="running",
            started_at=datetime.now(tz=UTC),
            created_by="system",
        )
    )
    return int(result.inserted_primary_key[0])


def _create_attachment_file_result(
    conn,
    *,
    job_id: int,
    notice_no: str,
    filename: str,
    url: str,
) -> int:
    result = conn.execute(
        attachment_fetch_files.insert().values(
            job_id=job_id,
            notice_no=notice_no,
            filename=filename,
            url=url,
            status="pending",
        )
    )
    return int(result.inserted_primary_key[0])


def _update_attachment_file_result(
    conn,
    file_id: int,
    *,
    status: str,
    upload_id: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        update(attachment_fetch_files)
        .where(attachment_fetch_files.c.id == file_id)
        .values(
            status=status,
            upload_id=upload_id,
            error=error,
            updated_at=datetime.now(tz=UTC),
        )
    )


def _finish_attachment_job(conn, job_id: int, status: str) -> None:
    conn.execute(
        update(attachment_fetch_jobs)
        .where(attachment_fetch_jobs.c.id == job_id)
        .values(status=status, finished_at=datetime.now(tz=UTC))
    )


def _attachment_file_models(conn, job_id: int) -> list[AttachmentFetchFileResult]:
    rows = conn.execute(
        select(attachment_fetch_files)
        .where(attachment_fetch_files.c.job_id == job_id)
        .order_by(attachment_fetch_files.c.id)
    ).mappings().all()
    return [
        AttachmentFetchFileResult(
            id=int(row["id"]),
            filename=str(row["filename"]),
            url=str(row["url"]),
            status=row["status"],
            upload_id=row.get("upload_id"),
            error=row.get("error"),
            source_ref="g2b_attachment",
        )
        for row in rows
    ]


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


@router.post("/{notice_no}/attachments/fetch", response_model=AttachmentFetchResponse)
def fetch_g2b_attachments(notice_no: str) -> AttachmentFetchResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row, analysis, document_automation = _load_or_create_document_automation(
            conn,
            notice_no,
        )
        attachments = iter_g2b_attachments(row["raw"])
        job_id = _create_attachment_job(conn, notice_no)
        fetched: list[UploadedDocument] = []
        errors: list[dict[str, Any]] = []

        # 재실행은 진짜 "재시도"여야 한다 → 이전 첨부 오류를 먼저 해소(resolved)하고,
        # 이번 실행에서 여전히 실패하는 것만 다시 기록한다. 이렇게 해야 에이전트 복구 후
        # 재분석 시 "서류 처리 오류 N건" 카운트가 실제로 줄어든다.
        conn.execute(
            update(notice_errors)
            .where(
                notice_errors.c.notice_no == notice_no,
                notice_errors.c.resolved_at.is_(None),
                notice_errors.c.stage.in_(
                    ("g2b_attachment_fetch", "g2b_attachment_analysis")
                ),
            )
            .values(resolved_at=datetime.now(tz=UTC))
        )

        existing_uploads = [
            item
            for item in (document_automation.get("uploads") or [])
            if isinstance(item, dict)
        ]
        existing_by_name = {
            str(item.get("name") or ""): item
            for item in existing_uploads
            if item.get("source_ref") == "g2b_attachment"
        }

        def _is_hwp(name: str) -> bool:
            return (
                "." in name
                and name.rsplit(".", 1)[-1].strip().lower() in {"hwp", "hwpx"}
            )

        def _existing_healthy(name: str) -> bool:
            """이미 받은 g2b 첨부가 '정상'인지(=재처리 불필요) 판정.

            정상 = 텍스트 추출 오류가 없고 파일이 디스크에 존재. 이전 실패(에이전트
            미연결 등)나 경로 이전(컨테이너→호스트)으로 파일이 없으면 재다운로드/재분석한다.
            또한 텍스트 추출 대상(pdf/hwp)인데 text_excerpt가 없으면(구버전 업로드) 본문 기반
            서류 판정을 위해 재처리한다.
            """
            item = existing_by_name.get(name)
            if not item:
                return False
            up = UploadedDocument.model_validate(item)
            on_disk = bool(up.storage_path) and Path(up.storage_path).exists()
            if up.text_extract_error or not on_disk:
                return False
            ext = name.rsplit(".", 1)[-1].strip().lower() if "." in name else ""
            if ext in {"pdf", "hwp", "hwpx"} and not up.text_excerpt:
                return False
            return True

        # HWP 에이전트 health를 한 번만 확인 → 미연결 시 파일마다 connect 재시도로
        # 시간 낭비하지 않고, 모호한 경고 N건을 명확한 1건으로 축약한다.
        # 새로 받을 .hwp뿐 아니라 '재처리 대상'(이전 실패/파일 유실)도 포함해 판단한다.
        hwp_client = _make_hwp_agent_client()
        needs_hwp = any(
            _is_hwp(a.filename) and not _existing_healthy(a.filename)
            for a in attachments
        )
        hwp_ok: bool | None = hwp_client.health() if needs_hwp else None
        hwp_unreachable = 0

        updated_docs = document_automation
        for attachment in attachments:
            file_id = _create_attachment_file_result(
                conn,
                job_id=job_id,
                notice_no=notice_no,
                filename=attachment.filename,
                url=attachment.url,
            )
            existing = existing_by_name.get(attachment.filename)
            if existing and _existing_healthy(attachment.filename):
                existing_upload = UploadedDocument.model_validate(existing)
                fetched.append(existing_upload)
                _update_attachment_file_result(
                    conn,
                    file_id,
                    status="skipped",
                    upload_id=existing_upload.id,
                )
                continue
            if existing:
                # 이전 실패/유실 → 오래된 업로드 항목을 제거하고 아래에서 새로 받는다.
                updated_docs, _ = remove_from_document_automation(
                    updated_docs, UploadedDocument.model_validate(existing).id
                )

            try:
                downloaded = download_g2b_attachment(attachment)
                saved = save_stream(
                    bytes_stream(downloaded.content),
                    notice_no=notice_no,
                    original_name=attachment.filename,
                )
                analysis_meta = analyze_upload(
                    saved=saved,
                    original_name=attachment.filename,
                    checklist=list(updated_docs.get("checklist") or []),
                    explicit_item_id=None,
                    hwp_client=hwp_client,
                    hwp_available=hwp_ok,
                )
                resolved_item_id = str(analysis_meta.pop("item_id") or "") or None
                uploaded = build_metadata(
                    saved,
                    original_name=attachment.filename,
                    mime=downloaded.mime,
                    item_id=resolved_item_id,
                    source_ref="g2b_attachment",
                    **analysis_meta,
                )
                updated_docs = merge_into_document_automation(updated_docs, uploaded)
                fetched.append(uploaded)
                _update_attachment_file_result(
                    conn,
                    file_id,
                    status="success",
                    upload_id=uploaded.id,
                    error=uploaded.text_extract_error,
                )
                if uploaded.text_extract_error:
                    if (
                        hwp_ok is False
                        and uploaded.text_extract_error == "HWP 에이전트 미연결"
                    ):
                        # 미연결은 루프 후 단일 요약 경고로 합친다 (파일별 중복 방지).
                        hwp_unreachable += 1
                    else:
                        errors.append(
                            {
                                "stage": "g2b_attachment_analysis",
                                "severity": "warning",
                                "source": "upload_analysis",
                                "file_name": attachment.filename,
                                "url": attachment.url,
                                "detail": uploaded.text_extract_error,
                            }
                        )
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
                errors.append(
                    {
                        "stage": "g2b_attachment_fetch",
                        "source": "g2b",
                        "file_name": attachment.filename,
                        "url": attachment.url,
                        "detail": detail,
                    }
                )
                _update_attachment_file_result(
                    conn,
                    file_id,
                    status="failed",
                    error=detail,
                )

        if hwp_unreachable:
            errors.append(
                {
                    "stage": "g2b_attachment_analysis",
                    "severity": "warning",
                    "source": "upload_analysis",
                    "detail": (
                        f"HWP 에이전트 미연결 ({hwp_client.base_url}) — "
                        "데스크톱 에이전트를 실행한 뒤 첨부 재분석을 다시 실행하세요. "
                        f"영향 .hwp {hwp_unreachable}건"
                    ),
                }
            )

        if not attachments:
            errors.append(
                {
                    "stage": "g2b_attachment_fetch",
                    "source": "g2b",
                    "detail": "G2B raw에 지원 가능한 첨부 URL이 없습니다.",
                }
            )

        # document_automation["errors"]는 UI가 읽는 저장소다. append만 하면 과거 실패가
        # 영원히 누적되므로, 이 엔드포인트가 만드는 단계(fetch/analysis)의 묵은 오류는
        # 버리고 이번 실행 결과로 교체한다. 다른 단계(autofill 등) 오류는 보존.
        _owned_stages = {"g2b_attachment_fetch", "g2b_attachment_analysis"}
        preserved_errors = [
            e
            for e in (updated_docs.get("errors") or [])
            if isinstance(e, dict) and e.get("stage") not in _owned_stages
        ]
        updated_docs = dict(updated_docs)
        updated_docs["errors"] = preserved_errors + errors
        if errors:
            _record_errors(conn, notice_no, errors)

        # 첨부 본문 반영: 방금 받은 첨부의 text_excerpt를 근거로 체크리스트(필수/필요)를 재판정.
        # analyze_document_requirements는 uploads/exports/수동변경을 보존하되 errors는 자체
        # 생성하므로, 위에서 관리한 errors를 합쳐 보존한다.
        managed_errors = list(updated_docs.get("errors") or [])
        refreshed_row = dict(row)
        refreshed_analysis = dict(analysis)
        refreshed_analysis["document_automation"] = updated_docs
        refreshed_row["analysis"] = refreshed_analysis
        reevaluated = analyze_document_requirements(refreshed_row)
        reeval_errors = [
            e for e in (reevaluated.get("errors") or []) if isinstance(e, dict)
        ]
        reevaluated["errors"] = managed_errors + reeval_errors
        updated_docs = reevaluated

        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        job_status = "completed_with_errors" if errors else "completed"
        _finish_attachment_job(conn, job_id, job_status)
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(status=advance_status(row["status"], "attachments_fetched"))
        )
        return AttachmentFetchResponse(
            notice_no=notice_no,
            job_id=job_id,
            status=job_status,
            files=_attachment_file_models(conn, job_id),
            fetched=fetched,
            errors=errors,
        )


@router.post("/{notice_no}/documents/uploads", response_model=UploadResponse)
async def upload_document(
    notice_no: str,
    file: UploadFile = File(...),
    item_id: str | None = Form(default=None),
) -> UploadResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _, analysis, document_automation = _load_document_automation(conn, notice_no)

        saved = save_stream(
            file.file,
            notice_no=notice_no,
            original_name=file.filename or "upload.bin",
        )
        analysis_meta = analyze_upload(
            saved=saved,
            original_name=file.filename or "upload.bin",
            checklist=list(document_automation.get("checklist") or []),
            explicit_item_id=item_id,
            hwp_client=_make_hwp_agent_client(),
        )
        resolved_item_id = str(analysis_meta.pop("item_id") or "") or None
        uploaded = build_metadata(
            saved,
            original_name=file.filename or "upload.bin",
            mime=file.content_type,
            item_id=resolved_item_id,
            **analysis_meta,
        )
        updated_docs = merge_into_document_automation(document_automation, uploaded)
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return UploadResponse(notice_no=notice_no, uploaded=uploaded)


@router.post("/{notice_no}/documents/import-common/{upload_id}", response_model=UploadResponse)
def import_common_document(notice_no: str, upload_id: str) -> UploadResponse:
    common = get_common_upload(upload_id)
    if common is None:
        raise HTTPException(status_code=404, detail="common upload not found")
    engine = require_engine()
    with engine.begin() as conn:
        _, analysis, document_automation = _load_document_automation(conn, notice_no)
        imported = clone_common_upload_for_notice(common)
        updated_docs = merge_into_document_automation(document_automation, imported)
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return UploadResponse(notice_no=notice_no, uploaded=imported)

@router.get("/{notice_no}/documents/uploads", response_model=UploadListResponse)
def list_document_uploads(notice_no: str) -> UploadListResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _, _, document_automation = _load_document_automation(conn, notice_no)
        items = [
            UploadedDocument.model_validate(item)
            for item in (document_automation.get("uploads") or [])
            if isinstance(item, dict)
        ]
        return UploadListResponse(notice_no=notice_no, items=items)


@router.delete("/{notice_no}/documents/uploads/{upload_id}")
def delete_document_upload(notice_no: str, upload_id: str) -> dict[str, Any]:
    engine = require_engine()
    with engine.begin() as conn:
        _, analysis, document_automation = _load_document_automation(conn, notice_no)
        updated_docs, removed = remove_from_document_automation(document_automation, upload_id)
        if removed is None:
            raise HTTPException(status_code=404, detail="upload not found")
        if removed.get("source_ref") != "common_library":
            delete_file(str(removed.get("storage_path") or ""))
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return {"notice_no": notice_no, "deleted": upload_id}


@router.get("/{notice_no}/documents/uploads/{upload_id}/download")
def download_document_upload(notice_no: str, upload_id: str) -> FileResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _, _, document_automation = _load_document_automation(conn, notice_no)
        for item in document_automation.get("uploads") or []:
            if isinstance(item, dict) and item.get("id") == upload_id:
                storage_path = str(item.get("storage_path") or "")
                if not storage_path or not os.path.isfile(storage_path):
                    raise HTTPException(status_code=410, detail="upload file missing on disk")
                return FileResponse(
                    storage_path,
                    media_type=str(item.get("mime") or "application/octet-stream"),
                    filename=str(item.get("name") or upload_id),
                )
        raise HTTPException(status_code=404, detail="upload not found")


@router.post("/{notice_no}/documents/exports/{kind}", response_model=ExportResponse)
def export_document(
    notice_no: str,
    kind: ExportKind,
    body: ExportCreateRequest | None = Body(default=None),
) -> ExportResponse:
    engine = require_engine()
    validation_failure: list[dict[str, Any]] | None = None
    response: ExportResponse | None = None
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        draft = get_technical_compliance_draft(document_automation)
        title = str(row["title"] or notice_no)
        if kind == "proposal_hwp":
            raise HTTPException(status_code=400, detail=f"unsupported export kind: {kind}")
        spec_rows = _list_spec_item_rows(conn, notice_no, include_ignored=False)
        pre_errors, pre_warnings = validate_pre_compose(
            document_automation,
            spec_rows=spec_rows,
            values={},
            target_item_ids={"technical_compliance"},
        )
        if kind == "hwp" and pre_errors:
            updated_docs = dict(document_automation)
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + pre_errors
            _record_errors(conn, notice_no, pre_errors)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            validation_failure = pre_errors
        elif kind == "excel":
            export = build_excel(
                notice_no=notice_no,
                draft=draft,
                title=title,
                version=(body.version if body else "compliance_excel_v2"),
                notice_meta={
                    "org_name": row.get("org_name") or "",
                    "status": row.get("status") or "",
                },
                validation_warnings=pre_warnings,
            )
        elif kind == "hwp":
            export = build_hwp(
                client=_make_hwp_agent_client(),
                notice_no=notice_no,
                draft=draft,
                title=title,
            )
            if pre_warnings:
                export = export.model_copy(
                    update={"validation_status": "warning", "validation_errors": pre_warnings}
                )
        else:
            raise HTTPException(status_code=400, detail=f"unsupported export kind: {kind}")
        if validation_failure:
            response = None
        else:
            export = _record_export(conn, notice_no, export)
            updated_docs = merge_export_into_document_automation(document_automation, export)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            response = ExportResponse(notice_no=notice_no, export=export)
    if validation_failure:
        raise HTTPException(
            status_code=409,
            detail={"message": "pre-compose validation failed", "errors": validation_failure},
        )
    assert response is not None
    return response


@router.post("/{notice_no}/documents/hwp-compose", response_model=HwpComposeResponse)
def compose_hwp_documents(notice_no: str, body: HwpComposeRequest) -> HwpComposeResponse:
    engine = require_engine()
    validation_failure: list[dict[str, Any]] | None = None
    response: HwpComposeResponse | None = None
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        spec_rows = _list_spec_item_rows(conn, notice_no, include_ignored=False)

        errors: list[dict[str, Any]] = []
        target_ids: set[str] = set()
        if body.include_bid_form:
            target_ids.add("bid_form")
        if body.include_technical_compliance:
            target_ids.add("technical_compliance")
        pre_errors, pre_warnings = validate_pre_compose(
            document_automation,
            spec_rows=spec_rows,
            values=body.values,
            target_item_ids=target_ids,
        )
        if pre_errors:
            updated_docs = dict(document_automation)
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + pre_errors
            _record_errors(conn, notice_no, pre_errors)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            validation_failure = pre_errors
        if validation_failure:
            response = None
        else:
            errors.extend(pre_warnings)
        bid_result: HwpComposeBidFormResult | None = None
        export = None
        updated_analysis = dict(analysis)
        updated_docs = _replace_technical_draft_from_spec_items(document_automation, spec_rows)
        client = _make_hwp_agent_client()

        if not validation_failure and body.include_bid_form:
            output_path = body.bid_form_output_path or f"output/autofilled_{notice_no}.hwp"
            draft_values = {}
            drafts = updated_docs.get("drafts") if isinstance(updated_docs, dict) else None
            if isinstance(drafts, dict) and isinstance(drafts.get("bid_form_values"), dict):
                values = drafts["bid_form_values"].get("values")
                if isinstance(values, dict):
                    draft_values = {key: str(value) for key, value in values.items()}
            merged_values = {
                **_company_defaults(row),
                **draft_values,
                **compose_hwp_values(row, spec_rows, body.values),
            }
            try:
                outcome = client.autofill_bid_form(
                    template_path=body.bid_form_template_path,
                    output_path=output_path,
                    values=merged_values,
                    visible=body.visible,
                )
                updated_analysis = attach_bid_form_result(
                    updated_analysis | {"document_automation": updated_docs},
                    template_path=outcome.template_path,
                    output_path=outcome.output_path,
                    replaced=outcome.replaced,
                    missing=outcome.missing,
                    remaining_placeholders=outcome.remaining_placeholders,
                )
                updated_docs = dict(updated_analysis.get("document_automation") or updated_docs)
                bid_result = HwpComposeBidFormResult(
                    template_path=outcome.template_path,
                    output_path=outcome.output_path,
                    replaced=outcome.replaced,
                    missing=outcome.missing,
                    remaining_placeholders=outcome.remaining_placeholders,
                )
                if outcome.remaining_placeholders:
                    errors.append(
                        {
                            "stage": "bid_form.placeholders",
                            "severity": "warning",
                            "detail": "입찰참가신청서 HWP에 남은 placeholder가 있습니다",
                            "remaining_placeholders": outcome.remaining_placeholders,
                        }
                    )
            except HwpAgentError as exc:
                errors.append({"stage": "bid_form", "detail": str(exc)})

        if not validation_failure and body.include_technical_compliance:
            try:
                draft = get_technical_compliance_draft(updated_docs)
                export = build_hwp(
                    client=client,
                    notice_no=notice_no,
                    draft=draft,
                    title=str(row["title"] or notice_no),
                )
                if pre_warnings:
                    export = export.model_copy(
                        update={"validation_status": "warning", "validation_errors": pre_warnings}
                    )
                export = _record_export(conn, notice_no, export)
                updated_docs = merge_export_into_document_automation(updated_docs, export)
            except HTTPException as exc:
                errors.append({"stage": "technical_compliance", "detail": str(exc.detail)})

        if not validation_failure:
            existing_errors = list(updated_docs.get("errors") or [])
            updated_docs["errors"] = existing_errors + errors
            _record_errors(conn, notice_no, errors)
            updated_analysis["document_automation"] = updated_docs
            next_status = advance_status(row["status"], "hwp_composed") if export else row["status"]
            remaining = bid_result.remaining_placeholders if bid_result else []
            blocking_errors = [item for item in errors if item.get("severity", "error") == "error"]
            if (
                not blocking_errors
                and not remaining
                and body.include_bid_form
                and bid_result is not None
            ):
                next_status = advance_status(next_status, "form_filled")

            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=updated_analysis, status=next_status)
            )
            response = HwpComposeResponse(
                notice_no=notice_no,
                status=next_status,
                bid_form=bid_result,
                technical_compliance=export,
                remaining_placeholders=remaining,
                errors=errors,
            )
    if validation_failure:
        raise HTTPException(
            status_code=409,
            detail={"message": "pre-compose validation failed", "errors": validation_failure},
        )
    assert response is not None
    return response


@router.post("/{notice_no}/documents/proposal-compose", response_model=ProposalComposeResponse)
def compose_proposal_document(
    notice_no: str,
    body: ProposalComposeRequest,
) -> ProposalComposeResponse:
    engine = require_engine()
    validation_failure: list[dict[str, Any]] | None = None
    response: ProposalComposeResponse | None = None
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        spec_rows = _list_spec_item_rows(conn, notice_no, include_ignored=True)
        pre_errors, pre_warnings = validate_pre_compose(
            document_automation,
            spec_rows=spec_rows,
            values=body.values_override,
            target_item_ids={"bid_form", "technical_compliance", "proposal"},
        )
        if pre_errors:
            updated_docs = dict(document_automation)
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + pre_errors
            _record_errors(conn, notice_no, pre_errors)
            _persist_document_automation(conn, notice_no, analysis, updated_docs)
            validation_failure = pre_errors
        if validation_failure:
            response = None
        else:
            errors: list[dict[str, Any]] = list(pre_warnings)

        updated_docs = dict(document_automation)
        drafts = dict(updated_docs.get("drafts") or {})
        proposal = build_proposal_payload(
            row=row,
            spec_rows=spec_rows,
            document_automation=updated_docs,
            company_values=_company_defaults(row),
            overrides=body.values_override,
        )
        drafts["proposal"] = proposal
        updated_docs["drafts"] = drafts

        export = None
        remaining: list[str] = []
        output_path = body.output_path or proposal_output_path(notice_no)
        if not validation_failure:
            try:
                outcome = _make_hwp_agent_client().compose_proposal(
                    template_path=body.template_path,
                    output_path=output_path,
                    values={key: str(value) for key, value in proposal["values"].items()},
                    sections=proposal["sections"],
                    tables=proposal["tables"],
                    visible=body.visible,
                )
                remaining = outcome.remaining_placeholders
                proposal["result"] = ProposalComposeResult(
                    output_path=outcome.output_path,
                    replaced=outcome.replaced,
                    missing=outcome.missing,
                    remaining_placeholders=outcome.remaining_placeholders,
                    section_count=outcome.section_count,
                    table_count=outcome.table_count,
                ).model_dump()
                export = build_proposal_export(
                    notice_no=notice_no,
                    output_path=outcome.output_path,
                    notes=f"sections={outcome.section_count}, tables={outcome.table_count}",
                )
                if remaining:
                    placeholder_warning = {
                        "stage": "proposal.placeholders",
                        "severity": "warning",
                        "detail": "제안서 HWP에 남은 placeholder가 있습니다",
                        "remaining_placeholders": remaining,
                    }
                    errors.append(placeholder_warning)
                    export = export.model_copy(
                        update={"validation_status": "warning", "validation_errors": errors}
                    )
                elif pre_warnings:
                    export = export.model_copy(
                        update={"validation_status": "warning", "validation_errors": pre_warnings}
                    )
                export = _record_export(conn, notice_no, export)
                updated_docs = merge_export_into_document_automation(updated_docs, export)
            except HwpAgentError as exc:
                errors.append({"stage": "proposal", "detail": str(exc)})

        drafts = dict(updated_docs.get("drafts") or {})
        drafts["proposal"] = proposal
        updated_docs["drafts"] = drafts
        if not validation_failure:
            updated_docs["errors"] = list(updated_docs.get("errors") or []) + errors
            _record_errors(conn, notice_no, errors)

            updated_analysis = dict(analysis)
            updated_analysis["document_automation"] = updated_docs
            next_status = advance_status(row["status"], "hwp_composed") if export else row["status"]
            conn.execute(
                update(bid_pipeline)
                .where(bid_pipeline.c.notice_no == notice_no)
                .values(analysis=updated_analysis, status=next_status)
            )
            response = ProposalComposeResponse(
                notice_no=notice_no,
                export=export,
                proposal=proposal,
                remaining_placeholders=remaining,
                errors=errors,
            )
    if validation_failure:
        raise HTTPException(
            status_code=409,
            detail={"message": "pre-compose validation failed", "errors": validation_failure},
        )
    assert response is not None
    return response


def _export_file_response(notice_no: str, meta: dict[str, Any]) -> FileResponse:
    kind = str(meta.get("kind") or "")
    output_path = str(meta.get("output_path") or "")
    if not output_path:
        raise HTTPException(status_code=404, detail="export output path missing")
    if not os.path.isfile(output_path):
        raise HTTPException(status_code=410, detail="export file missing on disk")
    suffix = "xlsx" if kind == "excel" else "hwp"
    name = "proposal" if kind == "proposal_hwp" else "compliance"
    return FileResponse(
        output_path,
        media_type=str(meta.get("mime") or "application/octet-stream"),
        filename=f"{notice_no}-{name}.{suffix}",
    )


@router.get("/{notice_no}/documents/exports/by-id/{export_id}/download")
def download_document_export_by_id(notice_no: str, export_id: int) -> FileResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _load_document_automation(conn, notice_no)
        meta = _lookup_export_by_id(conn, notice_no, export_id)
        if not meta:
            raise HTTPException(status_code=404, detail="export not found")
        return _export_file_response(notice_no, meta)


@router.get("/{notice_no}/documents/exports/{kind}/download")
def download_document_export(notice_no: str, kind: ExportKind) -> FileResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _, _, document_automation = _load_document_automation(conn, notice_no)
        draft_id = "proposal" if kind == "proposal_hwp" else "technical_compliance"
        meta = _lookup_active_export(conn, notice_no, kind=kind, draft_id=draft_id)
        if not meta:
            meta = lookup_export(document_automation, kind=kind, draft_id=draft_id)
        if not meta:
            raise HTTPException(
                status_code=404,
                detail=f"export not generated yet — POST /notices/{notice_no}/documents/exports/{kind} first",
            )
        return _export_file_response(notice_no, meta)


@router.post("/{notice_no}/grade", response_model=NoticeGradeResponse)
def grade_notice(
    notice_no: str,
    body: GradeRequest = Body(default=GradeRequest()),
) -> NoticeGradeResponse:
    """grade_notice_impl thin wrapper — 도메인 예외만 HTTPException으로 변환.

    실제 로직(SKU 매칭 / 자격 API 호출 / 3축 점수 / DB 저장 / Slack 알림)은
    [api/services/grading_runner.py](api/services/grading_runner.py)에 있다.
    스케줄러도 같은 grade_notice_impl을 직접 호출 (M5).
    """
    from api.services.grading_runner import (
        GradeInvalidStatusError,
        GradeNotFoundError,
        grade_notice_impl,
    )

    engine = require_engine()
    try:
        return grade_notice_impl(engine, notice_no, alert=body.alert)
    except GradeNotFoundError:
        raise HTTPException(status_code=404, detail="notice not found")
    except GradeInvalidStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _as_kst(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(ZoneInfo("Asia/Seoul"))


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _has_blocked_document(analysis: dict[str, Any] | None) -> bool:
    doc = (analysis or {}).get("document_automation")
    if not isinstance(doc, dict):
        return False
    checklist = doc.get("checklist")
    if not isinstance(checklist, list):
        return False
    return any(isinstance(item, dict) and item.get("status") == "blocked" for item in checklist)


def _is_ready_for_submission(analysis: dict[str, Any] | None) -> bool:
    doc = (analysis or {}).get("document_automation")
    return isinstance(doc, dict) and doc.get("ready_for_submission") is True


@router.get("/summary", response_model=NoticeSummary)
def get_notice_summary() -> NoticeSummary:
    """Saved notice work-queue counters for the /notices console."""
    engine = require_engine()
    now = datetime.now(tz=UTC)
    today_kst = now.astimezone(ZoneInfo("Asia/Seoul")).date()

    stmt = select(
        bid_pipeline.c.status,
        bid_pipeline.c.close_date,
        bid_pipeline.c.graded_at,
        bid_pipeline.c.analysis,
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()

    summary = NoticeSummary()
    for row in rows:
        close_date = _as_utc(row.get("close_date"))
        is_active = close_date is None or close_date >= now
        if is_active:
            summary.active_total += 1

            close_kst = _as_kst(close_date)
            if close_kst is not None:
                days_until_close = (close_kst.date() - today_kst).days
                if days_until_close == 0:
                    summary.closing_today += 1
                if 0 <= days_until_close <= 7:
                    summary.closing_7d += 1

        status = row.get("status")
        if status == "collected":
            summary.needs_analysis += 1
        if status == "analyzed" and row.get("graded_at") is None:
            summary.needs_grade += 1

        analysis = row.get("analysis") or {}
        if _is_ready_for_submission(analysis):
            summary.ready_for_submission += 1
        if _has_blocked_document(analysis):
            summary.blocked_documents += 1

    return summary


@router.get("/{notice_no}", response_model=NoticeRecord)
def get_notice(notice_no: str) -> NoticeRecord:
    engine = require_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")
        return _row_to_record(row)


_SORT_COLUMNS = {
    "close_date": bid_pipeline.c.close_date,
    "updated_at": bid_pipeline.c.updated_at,
    "base_price": bid_pipeline.c.base_price,
    "fit_score": bid_pipeline.c.fit_score,
    "score_total": bid_pipeline.c.score_total,
}
_TEXT_SEARCH_COLUMNS = (
    bid_pipeline.c.title,
    bid_pipeline.c.notice_no,
    bid_pipeline.c.org_name,
    bid_pipeline.c.assignee,
    bid_pipeline.c.category,
    bid_pipeline.c.top_sku_name,
    bid_pipeline.c.grade_reason,
    bid_pipeline.c.risk_note,
)


def _doc_automation_generated_at_expr(dialect_name: str):
    """analysis.document_automation.generated_at — Postgres JSONB / SQLite json_extract."""
    if dialect_name == "postgresql":
        return bid_pipeline.c.analysis["document_automation"]["generated_at"].astext
    # SQLite: analysis 컬럼이 JSON()으로 정의돼 TEXT로 저장 — json_extract로 path 추출
    return func.json_extract(bid_pipeline.c.analysis, "$.document_automation.generated_at")


def _doc_automation_uploads_count_expr(dialect_name: str):
    """uploads 배열 길이 — Postgres jsonb_array_length / SQLite json_array_length."""
    if dialect_name == "postgresql":
        return func.jsonb_array_length(
            bid_pipeline.c.analysis["document_automation"]["uploads"]
        )
    return func.json_array_length(
        func.json_extract(bid_pipeline.c.analysis, "$.document_automation.uploads")
    )


def _doc_automation_ready_expr(dialect_name: str):
    """ready_for_submission boolean."""
    if dialect_name == "postgresql":
        return bid_pipeline.c.analysis["document_automation"]["ready_for_submission"].astext
    return func.json_extract(
        bid_pipeline.c.analysis, "$.document_automation.ready_for_submission"
    )


def _apply_search_filters(
    stmt,
    *,
    dialect_name: str,
    q: str | None,
    status_list: list[str] | None,
    category_list: list[str] | None,
    bid_type_list: list[str] | None,
    source_list: list[str] | None,
    org_name: str | None,
    assignee: str | None,
    min_fit_score: int | None,
    max_fit_score: int | None,
    min_score_total: float | None,
    max_score_total: float | None,
    min_base_price: float | None,
    max_base_price: float | None,
    open_from: datetime | None,
    open_to: datetime | None,
    close_from: datetime | None,
    close_to: datetime | None,
    lifecycle: str,
    has_grade: bool | None,
    has_documents: bool | None,
    has_uploads: bool | None,
    ready_for_submission: bool | None,
    now_utc: datetime,
):
    """모든 필터를 WHERE 절에 누적해 stmt를 반환. 호출자가 정렬·페이지네이션을 별도로 적용."""
    if q:
        # 공백 무시 매칭: G2B 데이터의 띄어쓰기 변형에 대응.
        # 예) title "제 어기시험장치" ↔ q "제어기시험장치" 동일 취급.
        # 여러 단어 검색은 나라장터 AND 검색처럼 단어 순서가 바뀐 제목도 포함한다.
        tokens = [token.lower().replace(" ", "") for token in q.split() if token.strip()]
        if not tokens:
            tokens = [q.lower().replace(" ", "")]
        for token in tokens:
            if not token:
                continue
            like = f"%{token}%"
            stmt = stmt.where(
                or_(
                    *[
                        func.lower(func.replace(c, " ", "")).like(like)
                        for c in _TEXT_SEARCH_COLUMNS
                    ]
                )
            )
    if status_list:
        stmt = stmt.where(bid_pipeline.c.status.in_(status_list))
    if category_list:
        stmt = stmt.where(bid_pipeline.c.category.in_(category_list))
    if bid_type_list:
        stmt = stmt.where(bid_pipeline.c.bid_type.in_(bid_type_list))
    if source_list:
        stmt = stmt.where(bid_pipeline.c.source.in_(source_list))
    if org_name:
        stmt = stmt.where(func.lower(bid_pipeline.c.org_name).like(f"%{org_name.lower()}%"))
    if assignee:
        stmt = stmt.where(bid_pipeline.c.assignee == assignee)
    if min_fit_score is not None:
        stmt = stmt.where(bid_pipeline.c.fit_score >= min_fit_score)
    if max_fit_score is not None:
        stmt = stmt.where(bid_pipeline.c.fit_score <= max_fit_score)
    if min_score_total is not None:
        stmt = stmt.where(bid_pipeline.c.score_total >= min_score_total)
    if max_score_total is not None:
        stmt = stmt.where(bid_pipeline.c.score_total <= max_score_total)
    if min_base_price is not None:
        stmt = stmt.where(bid_pipeline.c.base_price >= min_base_price)
    if max_base_price is not None:
        stmt = stmt.where(bid_pipeline.c.base_price <= max_base_price)
    if open_from is not None:
        stmt = stmt.where(bid_pipeline.c.open_date >= open_from)
    if open_to is not None:
        stmt = stmt.where(bid_pipeline.c.open_date <= open_to)
    if close_from is not None:
        stmt = stmt.where(bid_pipeline.c.close_date >= close_from)
    if close_to is not None:
        stmt = stmt.where(bid_pipeline.c.close_date <= close_to)

    # lifecycle 분기 — :now는 UTC, close_date는 timestamptz로 저장돼 자동 비교 가능
    if lifecycle == "active":
        stmt = stmt.where(
            or_(
                bid_pipeline.c.close_date.is_(None),
                bid_pipeline.c.close_date >= now_utc,
            )
        )
    elif lifecycle == "closed":
        stmt = stmt.where(bid_pipeline.c.close_date < now_utc)
    elif lifecycle == "unknown":
        stmt = stmt.where(bid_pipeline.c.close_date.is_(None))
    # "all" → 추가 조건 없음

    if has_grade is True:
        stmt = stmt.where(bid_pipeline.c.graded_at.is_not(None))
    elif has_grade is False:
        stmt = stmt.where(bid_pipeline.c.graded_at.is_(None))

    if has_documents is True:
        stmt = stmt.where(_doc_automation_generated_at_expr(dialect_name).is_not(None))
    elif has_documents is False:
        stmt = stmt.where(_doc_automation_generated_at_expr(dialect_name).is_(None))

    if has_uploads is True:
        stmt = stmt.where(_doc_automation_uploads_count_expr(dialect_name) > 0)
    elif has_uploads is False:
        # uploads 없음 = 카운트 NULL(서류분석 안됨) 또는 0
        stmt = stmt.where(
            or_(
                _doc_automation_uploads_count_expr(dialect_name).is_(None),
                _doc_automation_uploads_count_expr(dialect_name) == 0,
            )
        )

    if ready_for_submission is True:
        ready_expr = _doc_automation_ready_expr(dialect_name)
        # Postgres astext는 "true"/"false" 문자열, SQLite json_extract는 boolean (1/0) 또는 'true'
        stmt = stmt.where(or_(cast(ready_expr, String) == "true", ready_expr == True))  # noqa: E712
    elif ready_for_submission is False:
        ready_expr = _doc_automation_ready_expr(dialect_name)
        stmt = stmt.where(
            or_(
                ready_expr.is_(None),
                cast(ready_expr, String) == "false",
                ready_expr == False,  # noqa: E712
            )
        )

    return stmt


def _apply_sort(stmt, sort: str, direction: str):
    col = _SORT_COLUMNS[sort]
    if direction == "desc":
        ordering = col.desc()
    else:
        ordering = col.asc()
    # NULL은 항상 뒤 (마감 임박순 기본 정렬에서 마감일 미확인 공고가 뒤로 가는 요구사항)
    ordering = nullslast(ordering)
    # 동률은 updated_at desc로 안정 정렬
    if sort != "updated_at":
        stmt = stmt.order_by(ordering, bid_pipeline.c.updated_at.desc())
    else:
        stmt = stmt.order_by(ordering, bid_pipeline.c.notice_no)
    return stmt


def _parse_csv(values: list[str] | None) -> list[str] | None:
    """`?status=a&status=b` 그리고 fallback으로 `?status=a,b` 모두 허용 — 빈 토큰 제거."""
    if not values:
        return None
    out: list[str] = []
    for v in values:
        if not v:
            continue
        for part in v.split(","):
            p = part.strip()
            if p:
                out.append(p)
    return out or None


@router.get("", response_model=NoticeListResponse)
def list_notices(
    q: str | None = Query(default=None, max_length=200, description="통합 키워드 부분일치"),
    status: list[str] | None = Query(default=None, description="상태 (다중 가능)"),
    category: list[str] | None = Query(default=None),
    bid_type: list[str] | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    org_name: str | None = Query(default=None, max_length=200),
    assignee: str | None = Query(default=None, max_length=80),
    min_fit_score: int | None = Query(default=None, ge=0, le=100),
    max_fit_score: int | None = Query(default=None, ge=0, le=100),
    min_score_total: float | None = Query(default=None, ge=0.0, le=1.0),
    max_score_total: float | None = Query(default=None, ge=0.0, le=1.0),
    min_base_price: float | None = Query(default=None, ge=0.0),
    max_base_price: float | None = Query(default=None, ge=0.0),
    open_from: datetime | None = Query(default=None),
    open_to: datetime | None = Query(default=None),
    close_from: datetime | None = Query(default=None),
    close_to: datetime | None = Query(default=None),
    lifecycle: str = Query(default="all", pattern="^(active|closed|unknown|all)$"),
    has_grade: bool | None = Query(default=None),
    has_documents: bool | None = Query(default=None),
    has_uploads: bool | None = Query(default=None),
    ready_for_submission: bool | None = Query(default=None),
    sort: str = Query(default="updated_at", pattern="^(close_date|updated_at|base_price|fit_score|score_total)$"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> NoticeListResponse:
    engine = require_engine()
    dialect_name = engine.dialect.name
    now_utc = datetime.now(tz=UTC)

    status_list = _parse_csv(status)
    category_list = _parse_csv(category)
    bid_type_list = _parse_csv(bid_type)
    source_list = _parse_csv(source)

    base_stmt = select(*_notice_select_columns())
    base_stmt = _apply_search_filters(
        base_stmt,
        dialect_name=dialect_name,
        q=q,
        status_list=status_list,
        category_list=category_list,
        bid_type_list=bid_type_list,
        source_list=source_list,
        org_name=org_name,
        assignee=assignee,
        min_fit_score=min_fit_score,
        max_fit_score=max_fit_score,
        min_score_total=min_score_total,
        max_score_total=max_score_total,
        min_base_price=min_base_price,
        max_base_price=max_base_price,
        open_from=open_from,
        open_to=open_to,
        close_from=close_from,
        close_to=close_to,
        lifecycle=lifecycle,
        has_grade=has_grade,
        has_documents=has_documents,
        has_uploads=has_uploads,
        ready_for_submission=ready_for_submission,
        now_utc=now_utc,
    )

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    paged_stmt = _apply_sort(base_stmt, sort, direction).limit(page_size).offset(
        (page - 1) * page_size
    )

    with engine.begin() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(paged_stmt).mappings().all()

    total_pages = math.ceil(total / page_size) if total else 0
    return NoticeListResponse(
        items=[_row_to_record(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
