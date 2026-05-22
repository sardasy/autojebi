import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, exists
from src.config import settings
from src.db.models import Bid, NotificationLog

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    """Alembic 마이그레이션을 head 까지 적용 (idempotent).

    create_all 폐기. lifespan과 스크립트에서 동일하게 호출.
    """
    from alembic.config import Config
    from alembic import command

    project_root = Path(__file__).resolve().parents[2]
    cfg_path = project_root / "alembic.ini"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)

    await asyncio.to_thread(command.upgrade, cfg, "head")
    logger.info("Alembic 마이그레이션 적용 완료 (head)")


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session


class BidRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def exists(self, source_id: str) -> bool:
        result = await self.session.execute(
            select(exists().where(Bid.source_id == source_id))
        )
        return result.scalar()

    async def save(self, bid: Bid) -> Bid:
        self.session.add(bid)
        await self.session.commit()
        await self.session.refresh(bid)
        return bid

    async def get_today_top_bids(self, limit: int = 10) -> list[Bid]:
        since = datetime.utcnow() - timedelta(hours=24)
        result = await self.session.execute(
            select(Bid)
            .where(Bid.created_at >= since)
            .where(Bid.relevance_score >= settings.relevance_threshold)
            .order_by(Bid.relevance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_bids(
        self,
        *,
        organization: str | None = None,
        category: str | None = None,
        label: str | None = None,
        days: int = 7,
        limit: int = 200,
    ) -> list[Bid]:
        """필터링 가능한 공고 조회. label 'none' 은 미라벨 필터."""
        since = datetime.utcnow() - timedelta(days=max(days, 1))
        stmt = (
            select(Bid)
            .where(Bid.created_at >= since)
            .order_by(Bid.relevance_score.desc().nulls_last(), Bid.created_at.desc())
            .limit(limit)
        )
        if organization:
            stmt = stmt.where(Bid.organization.ilike(f"%{organization}%"))
        if category:
            stmt = stmt.where(Bid.category == category)
        if label == "none":
            stmt = stmt.where(Bid.user_label.is_(None))
        elif label:
            stmt = stmt.where(Bid.user_label == label)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def log_notification(self, bid_id, channel: str, status: str = "sent"):
        log = NotificationLog(bid_id=bid_id, channel=channel, status=status)
        self.session.add(log)
        await self.session.commit()
