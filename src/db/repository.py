import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, exists, func, cast, Date, delete
from src.common.timez import utcnow
from src.config import settings
from src.db.models import AlertRule, Bid, BidAward, BidFeedback, NotificationLog, OrgPrior

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
        since = utcnow() - timedelta(hours=24)
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
        since = utcnow() - timedelta(days=max(days, 1))
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

    async def log_notification(self, bid_id, channel: str, status: str = "sent", rule_id=None):
        log = NotificationLog(bid_id=bid_id, channel=channel, status=status, rule_id=rule_id)
        self.session.add(log)
        await self.session.commit()


class BidAwardRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_awards(
        self,
        *,
        org: str | None = None,
        since: datetime | None = None,
        min_ratio: float | None = None,
        max_ratio: float | None = None,
        limit: int = 200,
    ) -> list[tuple[BidAward, "Bid | None"]]:
        stmt = (
            select(BidAward, Bid)
            .outerjoin(Bid, Bid.id == BidAward.bid_id)
            .order_by(BidAward.award_date.desc().nulls_last(), BidAward.created_at.desc())
            .limit(limit)
        )
        if org:
            stmt = stmt.where(Bid.organization.ilike(f"%{org}%"))
        if since is not None:
            stmt = stmt.where(BidAward.award_date >= since.date())
        if min_ratio is not None:
            stmt = stmt.where(BidAward.award_ratio >= min_ratio)
        if max_ratio is not None:
            stmt = stmt.where(BidAward.award_ratio <= max_ratio)
        rows = (await self.session.execute(stmt)).all()
        return [(a, b) for a, b in rows]

    async def get_for_bid(self, bid_id) -> BidAward | None:
        result = await self.session.execute(
            select(BidAward).where(BidAward.bid_id == bid_id).order_by(BidAward.award_date.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def ratio_histogram(self, bucket: float = 0.05) -> list[dict]:
        """낙찰률 히스토그램. bucket 단위로 그룹."""
        bucket_expr = (func.floor(BidAward.award_ratio / bucket) * bucket).label("b")
        rows = (await self.session.execute(
            select(bucket_expr, func.count())
            .where(BidAward.award_ratio.is_not(None))
            .group_by(bucket_expr)
            .order_by(bucket_expr)
        )).all()
        return [{"bucket": float(b), "count": int(c)} for b, c in rows]


class FeedbackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(self, bid_id, label: str, note: str | None, reviewer: str | None) -> BidFeedback:
        """(bid_id, reviewer) 유니크. 같은 리뷰어 재라벨링 시 기존 row 갱신.
        같은 트랜잭션에서 Bid.user_label / user_label_at 도 denormalize."""
        existing_result = await self.session.execute(
            select(BidFeedback).where(
                BidFeedback.bid_id == bid_id, BidFeedback.reviewer == reviewer
            )
        )
        feedback = existing_result.scalar_one_or_none()
        if feedback:
            feedback.label = label
            feedback.note = note
        else:
            feedback = BidFeedback(bid_id=bid_id, label=label, note=note, reviewer=reviewer)
            self.session.add(feedback)

        # 최신 라벨을 Bid 에 denormalize (조회 성능)
        bid_result = await self.session.execute(select(Bid).where(Bid.id == bid_id))
        bid = bid_result.scalar_one_or_none()
        if bid:
            bid.user_label = label
            bid.user_label_at = utcnow()

        await self.session.commit()
        await self.session.refresh(feedback)
        return feedback

    async def list_for_bid(self, bid_id) -> list[BidFeedback]:
        result = await self.session.execute(
            select(BidFeedback)
            .where(BidFeedback.bid_id == bid_id)
            .order_by(BidFeedback.created_at.desc())
        )
        return list(result.scalars().all())

    async def stats(self, days: int = 30) -> dict:
        since = utcnow() - timedelta(days=days)
        counts = dict(
            (await self.session.execute(
                select(BidFeedback.label, func.count())
                .where(BidFeedback.created_at >= since)
                .group_by(BidFeedback.label)
            )).all()
        )
        recent_rows = (await self.session.execute(
            select(BidFeedback, Bid)
            .join(Bid, Bid.id == BidFeedback.bid_id)
            .where(BidFeedback.created_at >= since)
            .order_by(BidFeedback.created_at.desc())
            .limit(20)
        )).all()
        recent = [
            {
                "bid_id": str(fb.bid_id),
                "title": bid.title,
                "label": fb.label,
                "reviewer": fb.reviewer,
                "created_at": fb.created_at.isoformat(),
            }
            for fb, bid in recent_rows
        ]
        return {"days": days, "counts": counts, "recent": recent}


class OrgPriorRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, organization: str) -> OrgPrior | None:
        result = await self.session.execute(
            select(OrgPrior).where(OrgPrior.organization == organization)
        )
        return result.scalar_one_or_none()

    async def upsert(self, organization: str, n_samples: int, p_relevant: float) -> OrgPrior:
        prior = await self.get(organization)
        if prior:
            prior.n_samples = n_samples
            prior.p_relevant = p_relevant
        else:
            prior = OrgPrior(organization=organization, n_samples=n_samples, p_relevant=p_relevant)
            self.session.add(prior)
        await self.session.commit()
        await self.session.refresh(prior)
        return prior

    async def all(self) -> list[OrgPrior]:
        result = await self.session.execute(select(OrgPrior))
        return list(result.scalars().all())


class AlertRuleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self) -> list[AlertRule]:
        result = await self.session.execute(select(AlertRule).order_by(AlertRule.created_at))
        return list(result.scalars().all())

    async def list_enabled(self) -> list[AlertRule]:
        result = await self.session.execute(
            select(AlertRule).where(AlertRule.enabled.is_(True)).order_by(AlertRule.created_at)
        )
        return list(result.scalars().all())

    async def get(self, rule_id) -> AlertRule | None:
        result = await self.session.execute(select(AlertRule).where(AlertRule.id == rule_id))
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> AlertRule:
        rule = AlertRule(**data)
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def update(self, rule_id, data: dict) -> AlertRule | None:
        rule = await self.get(rule_id)
        if not rule:
            return None
        for k, v in data.items():
            setattr(rule, k, v)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def delete(self, rule_id) -> bool:
        result = await self.session.execute(delete(AlertRule).where(AlertRule.id == rule_id))
        await self.session.commit()
        return (result.rowcount or 0) > 0


# 금액 버킷: ~1억 / 1억~10억 / 10억~50억 / 50억~ / 미정
PRICE_BUCKETS = [
    ("under_100m", None, 100_000_000),
    ("100m_1b", 100_000_000, 1_000_000_000),
    ("1b_5b", 1_000_000_000, 5_000_000_000),
    ("over_5b", 5_000_000_000, None),
]


class DashboardRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def stats(self, days: int = 30) -> dict:
        since = utcnow() - timedelta(days=days)
        base = select(Bid).where(Bid.created_at >= since).subquery()

        total = (await self.session.execute(
            select(func.count()).select_from(base)
        )).scalar() or 0

        avg_rel = (await self.session.execute(
            select(func.avg(Bid.relevance_score)).where(Bid.created_at >= since)
        )).scalar()

        awarded = (await self.session.execute(
            select(func.count()).select_from(Bid).where(
                Bid.created_at >= since, Bid.award_status == "awarded"
            )
        )).scalar() or 0

        new_count = (await self.session.execute(
            select(func.count()).select_from(Bid).where(
                Bid.created_at >= since, Bid.status == "new"
            )
        )).scalar() or 0

        by_source = dict(
            (await self.session.execute(
                select(Bid.source, func.count()).where(Bid.created_at >= since).group_by(Bid.source)
            )).all()
        )

        by_category = dict(
            (await self.session.execute(
                select(Bid.category, func.count())
                .where(Bid.created_at >= since, Bid.category.is_not(None))
                .group_by(Bid.category)
            )).all()
        )

        top_orgs_rows = (await self.session.execute(
            select(Bid.organization, func.count().label("c"))
            .where(Bid.created_at >= since, Bid.organization.is_not(None))
            .group_by(Bid.organization)
            .order_by(func.count().desc())
            .limit(10)
        )).all()
        top_organizations = [{"organization": o, "count": c} for o, c in top_orgs_rows]

        price_buckets: dict[str, int] = {}
        for label, low, high in PRICE_BUCKETS:
            stmt = select(func.count()).select_from(Bid).where(Bid.created_at >= since)
            if low is not None:
                stmt = stmt.where(Bid.estimated_price >= low)
            if high is not None:
                stmt = stmt.where(Bid.estimated_price < high)
            price_buckets[label] = (await self.session.execute(stmt)).scalar() or 0
        price_buckets["unknown"] = (await self.session.execute(
            select(func.count()).select_from(Bid).where(
                Bid.created_at >= since, Bid.estimated_price.is_(None)
            )
        )).scalar() or 0

        return {
            "days": days,
            "total": total,
            "avg_relevance": float(avg_rel) if avg_rel is not None else None,
            "awarded": awarded,
            "new_count": new_count,
            "by_source": by_source,
            "by_category": by_category,
            "top_organizations": top_organizations,
            "price_buckets": price_buckets,
        }

    async def timeseries(self, days: int = 30, metric: str = "count") -> list[dict]:
        since = utcnow() - timedelta(days=days)
        day = cast(Bid.created_at, Date).label("day")

        if metric == "avg_relevance":
            value = func.avg(Bid.relevance_score)
        elif metric == "sum_price":
            value = func.coalesce(func.sum(Bid.estimated_price), 0)
        else:
            value = func.count()

        rows = (await self.session.execute(
            select(day, value.label("v"))
            .where(Bid.created_at >= since)
            .group_by(day)
            .order_by(day)
        )).all()
        return [
            {"date": d.isoformat() if d else None, "value": float(v) if v is not None else 0}
            for d, v in rows
        ]

    async def award_trend(self, org: str | None = None, months: int = 12) -> list[dict]:
        since = utcnow() - timedelta(days=months * 31)
        month = func.date_trunc("month", BidAward.award_date).label("month")
        stmt = (
            select(month, func.avg(BidAward.award_ratio).label("avg_ratio"), func.count().label("n"))
            .where(BidAward.award_date.is_not(None), BidAward.award_date >= since.date())
        )
        if org:
            stmt = stmt.join(Bid, Bid.id == BidAward.bid_id).where(Bid.organization.ilike(f"%{org}%"))
        stmt = stmt.group_by(month).order_by(month)
        rows = (await self.session.execute(stmt)).all()
        return [
            {"month": m.date().isoformat() if m else None, "avg_award_ratio": float(r) if r else None, "n": int(n)}
            for m, r, n in rows
        ]
