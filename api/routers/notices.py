from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    cast,
    func,
    nullslast,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert

from api.auth import verify_api_key
from api.db import require_engine
from api.models.notices import (
    AutofillFormRequest,
    AutofillFormResponse,
    ChecklistUpdateRequest,
    DocumentAutomationResponse,
    DocumentAutomationResult,
    DocumentValidationResponse,
    ExportKind,
    ExportResponse,
    GradeRequest,
    MailExtractRequest,
    MailExtractResponse,
    NoticeAnalyzeResponse,
    NoticeGradeResponse,
    NoticeListResponse,
    NoticeRecord,
    NoticeSearchRequest,
    NoticeSearchResponse,
    NoticeSummary,
    NoticeUpsertRequest,
    NotifyRequest,
    NotifyResponse,
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
)
from api.services.exporters import (
    build_excel,
    build_hwp,
    get_technical_compliance_draft,
    lookup_export,
    merge_export_into_document_automation,
)
from api.services.hwp_agent_client import HwpAgentClient, HwpAgentError
from api.services.mail_extractor import extract_notice_from_mail
from api.services.notifications import TeamsNotifier
from api.services.routing import assignee_for_category
from api.services.status import can_transition, compute_notify_status
from api.services.uploads import (
    build_metadata,
    delete_file,
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
    )


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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


@router.post("/{notice_no}/analyze", response_model=NoticeAnalyzeResponse)
def analyze_notice(notice_no: str) -> NoticeAnalyzeResponse:
    engine = require_engine()

    with engine.begin() as conn:
        row = conn.execute(
            select(*bid_pipeline.c).where(bid_pipeline.c.notice_no == notice_no)
        ).mappings().one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="notice not found")

        current_status = row["status"]
        if not can_transition(current_status, "analyzed"):
            raise HTTPException(status_code=409, detail=f"invalid transition {current_status} -> analyzed")

        analyzer = ClaudeAnalyzer()
        result = analyzer.analyze_notice(notice_no=notice_no, title=row["title"], raw=row["raw"])
        assignee = assignee_for_category(result.category)

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
        if row["status"] not in {"analyzed", "form_filled"}:
            raise HTTPException(
                status_code=409,
                detail=f"documents can be analyzed only after notice analysis (current: {row['status']})",
            )

        document_automation = analyze_document_requirements(row)
        merged_analysis = dict(row["analysis"] or {})
        merged_analysis["document_automation"] = document_automation
        conn.execute(
            update(bid_pipeline)
            .where(bid_pipeline.c.notice_no == notice_no)
            .values(analysis=merged_analysis)
        )
        return DocumentAutomationResponse(
            notice_no=notice_no,
            document_automation=DocumentAutomationResult.model_validate(document_automation),
        )


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
        uploaded = build_metadata(
            saved,
            original_name=file.filename or "upload.bin",
            mime=file.content_type,
            item_id=item_id,
        )
        updated_docs = merge_into_document_automation(document_automation, uploaded)
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return UploadResponse(notice_no=notice_no, uploaded=uploaded)


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
def export_document(notice_no: str, kind: ExportKind) -> ExportResponse:
    engine = require_engine()
    with engine.begin() as conn:
        row, analysis, document_automation = _load_document_automation(conn, notice_no)
        draft = get_technical_compliance_draft(document_automation)
        title = str(row["title"] or notice_no)
        if kind == "excel":
            export = build_excel(notice_no=notice_no, draft=draft, title=title)
        elif kind == "hwp":
            export = build_hwp(
                client=_make_hwp_agent_client(),
                notice_no=notice_no,
                draft=draft,
                title=title,
            )
        else:
            raise HTTPException(status_code=400, detail=f"unsupported export kind: {kind}")
        updated_docs = merge_export_into_document_automation(document_automation, export)
        _persist_document_automation(conn, notice_no, analysis, updated_docs)
        return ExportResponse(notice_no=notice_no, export=export)


@router.get("/{notice_no}/documents/exports/{kind}/download")
def download_document_export(notice_no: str, kind: ExportKind) -> FileResponse:
    engine = require_engine()
    with engine.begin() as conn:
        _, _, document_automation = _load_document_automation(conn, notice_no)
        meta = lookup_export(document_automation, kind=kind)
        if not meta:
            raise HTTPException(
                status_code=404,
                detail=f"export not generated yet — POST /documents/exports/{kind} first",
            )
        output_path = str(meta.get("output_path") or "")
        if not output_path or not os.path.isfile(output_path):
            raise HTTPException(status_code=410, detail="export file missing on disk")
        suffix = "xlsx" if kind == "excel" else "hwp"
        return FileResponse(
            output_path,
            media_type=str(meta.get("mime") or "application/octet-stream"),
            filename=f"{notice_no}-compliance.{suffix}",
        )


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

    base_stmt = select(*bid_pipeline.c)
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
