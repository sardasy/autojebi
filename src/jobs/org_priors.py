"""기관별 피드백을 집계해 Beta(α=β=2) prior 를 갱신하는 야간 잡."""
import logging
from sqlalchemy import select, func
from src.db.repository import AsyncSessionLocal, OrgPriorRepository
from src.db.models import Bid, BidFeedback

logger = logging.getLogger(__name__)

ALPHA = 2.0
BETA = 2.0


async def update_org_priors() -> int:
    """라벨이 있는 모든 (기관, 라벨) 카운트를 집계해 prior 를 upsert.
    반환: 갱신한 기관 수."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Bid.organization, BidFeedback.label, func.count())
            .join(BidFeedback, BidFeedback.bid_id == Bid.id)
            .where(Bid.organization.is_not(None))
            .group_by(Bid.organization, BidFeedback.label)
        )).all()

        per_org: dict[str, dict[str, int]] = {}
        for org, label, count in rows:
            per_org.setdefault(org, {})[label] = int(count)

        repo = OrgPriorRepository(session)
        updated = 0
        for org, counts in per_org.items():
            pos = counts.get("relevant", 0) + counts.get("watch", 0)
            neg = counts.get("irrelevant", 0)
            n = pos + neg
            if n == 0:
                continue
            p = (ALPHA + pos) / (ALPHA + BETA + n)
            await repo.upsert(organization=org, n_samples=n, p_relevant=float(p))
            updated += 1

    logger.info("org_priors 갱신: %s 기관", updated)
    return updated
