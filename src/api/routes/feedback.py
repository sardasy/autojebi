import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import get_session, FeedbackRepository
from src.api.schemas import FeedbackCreate, FeedbackResponse, FeedbackStats

router = APIRouter(tags=["feedback"])

ALLOWED_LABELS = {"relevant", "irrelevant", "watch"}


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(payload: FeedbackCreate, session: AsyncSession = Depends(get_session)):
    if payload.label not in ALLOWED_LABELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"label must be one of {ALLOWED_LABELS}")
    repo = FeedbackRepository(session)
    return await repo.upsert(payload.bid_id, payload.label, payload.note, payload.reviewer)


@router.get("/bids/{bid_id}/feedback", response_model=list[FeedbackResponse])
async def list_feedback(bid_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = FeedbackRepository(session)
    return await repo.list_for_bid(bid_id)


@router.get("/feedback/stats", response_model=FeedbackStats)
async def feedback_stats(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    repo = FeedbackRepository(session)
    return await repo.stats(days=days)
