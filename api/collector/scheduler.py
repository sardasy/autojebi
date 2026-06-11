"""APScheduler — 매일 collect_hour:collect_minute (KST) G2B 수집 + M5 자동 grade."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from api.collector.pipeline import run_collection
from api.config import settings
from api.db import MissingDatabaseUrl, get_engine

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    """FastAPI lifespan에서 호출. SCHEDULER_ENABLED=false면 no-op."""
    global _scheduler
    if not settings.scheduler_enabled:
        log.info("[scheduler] disabled (SCHEDULER_ENABLED=false)")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(
        _daily_job,
        CronTrigger(
            hour=settings.collect_hour,
            minute=settings.collect_minute,
            timezone="Asia/Seoul",
        ),
        id="g2b_daily_collect",
        replace_existing=True,
    )
    log.info(
        "[scheduler] daily collect job scheduled at %02d:%02d KST",
        settings.collect_hour,
        settings.collect_minute,
    )

    # M5: 자동 grade job
    if settings.scheduler_grade_enabled and settings.grade_interval_minutes > 0:
        _scheduler.add_job(
            _grade_job,
            IntervalTrigger(minutes=settings.grade_interval_minutes),
            id="grade_periodic",
            replace_existing=True,
        )
        log.info(
            "[scheduler] grade job scheduled every %d minutes (batch limit %d)",
            settings.grade_interval_minutes,
            settings.grade_batch_limit,
        )
    else:
        log.info(
            "[scheduler] grade job disabled (SCHEDULER_GRADE_ENABLED=%s, GRADE_INTERVAL_MINUTES=%d)",
            settings.scheduler_grade_enabled,
            settings.grade_interval_minutes,
        )

    # 운영 안정화: qual_cache 만료 entry 청소 (lazy 무효화 보완)
    if settings.qual_cache_enabled:
        _scheduler.add_job(
            _qual_cache_cleanup_job,
            IntervalTrigger(hours=6),
            id="qual_cache_cleanup",
            replace_existing=True,
        )
        log.info("[scheduler] qual_cache cleanup job scheduled every 6 hours")

    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


def _daily_job() -> None:
    log.info("[scheduler] daily G2B collection start")
    try:
        engine = get_engine()
    except MissingDatabaseUrl as exc:
        log.error("[scheduler] DATABASE_URL not set: %s", exc)
        return
    try:
        stats = run_collection(engine)
        log.info("[scheduler] daily G2B collection done — %s", stats)
    except Exception:  # noqa: BLE001
        log.exception("[scheduler] daily G2B collection failed")


def _grade_job() -> None:
    """M5: analyzed AND graded_at IS NULL 공고를 batch_limit 만큼 자동 grade.

    grade_notice_impl을 직접 호출 (HTTP self-call 안함). 한 건 실패해도
    다음 건 계속. ANTHROPIC_API_KEY 없거나 Qdrant 미기동이어도 grade_notice_impl
    내부에서 폴백 처리되므로 안전.
    """
    log.info("[scheduler] grade job start")
    try:
        engine = get_engine()
    except MissingDatabaseUrl as exc:
        log.error("[scheduler] DATABASE_URL not set: %s", exc)
        return

    try:
        # 순환 의존 방지 — 본 함수가 import될 때 router/grading_runner를 끌어들이지 않도록 lazy.
        from sqlalchemy import select

        from api.routers.notices import bid_pipeline
        from api.services.grading_runner import (
            GradeError,
            grade_notice_impl,
        )

        with engine.connect() as conn:
            rows = conn.execute(
                select(bid_pipeline.c.notice_no)
                .where(bid_pipeline.c.status == "analyzed")
                .where(bid_pipeline.c.graded_at.is_(None))
                .order_by(bid_pipeline.c.created_at.asc())
                .limit(settings.grade_batch_limit)
            ).all()

        notice_nos = [r[0] for r in rows]
        if not notice_nos:
            log.info("[scheduler] grade job — no candidates")
            return
        log.info("[scheduler] grade job — %d candidates", len(notice_nos))

        ok = 0
        for notice_no in notice_nos:
            try:
                result = grade_notice_impl(engine, notice_no, alert=True)
                log.info(
                    "[scheduler] graded %s score_total=%.3f slack=%s",
                    notice_no,
                    result.score_total,
                    result.slack_delivered,
                )
                ok += 1
            except GradeError as exc:
                log.warning("[scheduler] skip %s: %s", notice_no, exc)
            except Exception:  # noqa: BLE001
                log.exception("[scheduler] grade %s failed", notice_no)

        log.info("[scheduler] grade job done — %d/%d succeeded", ok, len(notice_nos))
    except Exception:  # noqa: BLE001
        log.exception("[scheduler] grade job batch failed")


def _qual_cache_cleanup_job() -> None:
    """만료된 qual_cache entry 제거. 6시간 간격."""
    try:
        from api.services import qual_cache

        removed = qual_cache.cleanup_expired()
        log.info("[scheduler] qual_cache cleanup — removed %d expired entries", removed)
    except Exception:  # noqa: BLE001
        log.exception("[scheduler] qual_cache cleanup failed")
