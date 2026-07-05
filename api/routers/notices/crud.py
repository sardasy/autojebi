"""공고 CRUD — upsert / E2E cleanup / summary / 목록 검색 / 단건 조회."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import (
    String,
    cast,
    delete,
    func,
    nullslast,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert

from api.config import settings
from api.db import Conn, require_engine
from api.models.notices import (
    E2ECleanupResponse,
    NoticeListResponse,
    NoticeRecord,
    NoticeSummary,
    NoticeUpsertRequest,
)
from api.services.uploads import delete_file
from api.tables import (
    attachment_fetch_files,
    attachment_fetch_jobs,
    bid_pipeline,
    notice_errors,
    notice_exports,
    notice_spec_items,
)

from ._common import _notice_select_columns, _row_to_record, require_notice

router = APIRouter()


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
def get_notice_summary(conn: Conn) -> NoticeSummary:
    """Saved notice work-queue counters for the /notices console."""
    now = datetime.now(tz=UTC)
    today_kst = now.astimezone(ZoneInfo("Asia/Seoul")).date()

    stmt = select(
        bid_pipeline.c.status,
        bid_pipeline.c.close_date,
        bid_pipeline.c.graded_at,
        bid_pipeline.c.analysis,
    )
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
    conn: Conn,
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
    dialect_name = conn.dialect.name
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


@router.get("/{notice_no}", response_model=NoticeRecord)
def get_notice(notice_no: str, conn: Conn) -> NoticeRecord:
    row = require_notice(conn, notice_no)
    return _row_to_record(row)
