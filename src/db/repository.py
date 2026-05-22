from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, exists
from src.config import settings
from src.db.models import Base, Bid, NotificationLog

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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

    async def log_notification(self, bid_id, channel: str, status: str = "sent"):
        log = NotificationLog(bid_id=bid_id, channel=channel, status=status)
        self.session.add(log)
        await self.session.commit()
