from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.config import settings
from src.jobs.org_priors import update_org_priors

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def setup_scheduler(daily_job):
    scheduler.add_job(
        daily_job,
        trigger="cron",
        hour=settings.collect_schedule_hour,
        minute=settings.collect_schedule_minute,
        id="daily_collect",
        replace_existing=True,
    )
    scheduler.add_job(
        update_org_priors,
        trigger="cron",
        hour=2,
        minute=30,
        id="nightly_org_priors",
        replace_existing=True,
    )
    return scheduler
