from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.config import settings

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
    return scheduler
