import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import get_session, BidAwardRepository
from src.api.schemas import AwardResponse, RatioBucket

router = APIRouter(tags=["awards"])


def _to_response(award, bid) -> AwardResponse:
    return AwardResponse(
        id=award.id,
        bid_id=award.bid_id,
        source=award.source,
        source_award_id=award.source_award_id,
        source_bid_id=award.source_bid_id,
        winner_name=award.winner_name,
        winner_biz_no=award.winner_biz_no,
        award_price=award.award_price,
        award_date=award.award_date.isoformat() if award.award_date else None,
        participant_count=award.participant_count,
        award_ratio=award.award_ratio,
        bid_title=bid.title if bid else None,
        bid_organization=bid.organization if bid else None,
        bid_estimated_price=bid.estimated_price if bid else None,
        created_at=award.created_at,
    )


@router.get("/awards", response_model=list[AwardResponse])
async def list_awards(
    org: str | None = Query(default=None),
    days: int = Query(default=365, ge=1, le=1825),
    min_ratio: float | None = Query(default=None, ge=0),
    max_ratio: float | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    repo = BidAwardRepository(session)
    since = datetime.utcnow() - timedelta(days=days)
    rows = await repo.list_awards(
        org=org, since=since, min_ratio=min_ratio, max_ratio=max_ratio, limit=limit
    )
    return [_to_response(a, b) for a, b in rows]


@router.get("/awards/ratio-histogram", response_model=list[RatioBucket])
async def ratio_histogram(
    bucket: float = Query(default=0.05, gt=0, le=1.0),
    session: AsyncSession = Depends(get_session),
):
    repo = BidAwardRepository(session)
    return await repo.ratio_histogram(bucket=bucket)


@router.get("/bids/{bid_id}/award", response_model=AwardResponse)
async def get_award_for_bid(bid_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = BidAwardRepository(session)
    award = await repo.get_for_bid(bid_id)
    if not award:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no award found for this bid")
    return _to_response(award, getattr(award, "bid", None))
