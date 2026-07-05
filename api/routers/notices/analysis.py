"""공고 분석 — Claude 분석 / Teams 알림 / 3축 grading."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import select, update

from api.db import require_engine
from api.models.notices import (
    GradeRequest,
    NoticeAnalyzeResponse,
    NoticeGradeResponse,
    NotifyRequest,
    NotifyResponse,
)
from api.services.claude_analyzer import ClaudeAnalyzer
from api.services.notifications import TeamsNotifier
from api.services.routing import assignee_for_category
from api.services.status import can_transition, compute_notify_status
from api.tables import bid_pipeline

from ._common import _notice_select_columns, _record_errors

router = APIRouter()


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
