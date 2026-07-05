"""APScheduler jobs.

G2B collection is intentionally not scheduled anymore. The notices screen uses
request-driven live search against the G2B API instead of collecting into the
local bid_pipeline table first.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from api.config import settings
from api.db import MissingDatabaseUrl, get_engine

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    """Start non-collection background jobs from FastAPI lifespan."""
    global _scheduler
    if not settings.scheduler_enabled:
        log.info("[scheduler] disabled (SCHEDULER_ENABLED=false)")
        return
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    log.info("[scheduler] G2B collection job disabled; live search is request-driven")

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


def _grade_job() -> None:
    """Grade analyzed notices in small batches."""
    log.info("[scheduler] grade job start")
    try:
        engine = get_engine()
    except MissingDatabaseUrl as exc:
        log.error("[scheduler] DATABASE_URL not set: %s", exc)
        return

    try:
        from sqlalchemy import select

        from api.services.grading_runner import (
            GradeError,
            grade_notice_impl,
        )
        from api.tables import bid_pipeline

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
            log.info("[scheduler] grade job: no candidates")
            return
        log.info("[scheduler] grade job: %d candidates", len(notice_nos))

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
            except Exception:
                log.exception("[scheduler] grade %s failed", notice_no)

        log.info("[scheduler] grade job done: %d/%d succeeded", ok, len(notice_nos))
    except Exception:
        log.exception("[scheduler] grade job batch failed")


def _qual_cache_cleanup_job() -> None:
    """Remove expired qualification cache entries."""
    try:
        from api.services import qual_cache

        removed = qual_cache.cleanup_expired()
        log.info("[scheduler] qual_cache cleanup: removed %d expired entries", removed)
    except Exception:
        log.exception("[scheduler] qual_cache cleanup failed")
