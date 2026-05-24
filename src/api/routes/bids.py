import asyncio
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import get_session, BidRepository
from src.api.schemas import BidResponse

router = APIRouter(tags=["bids"])


@router.get("/bids", response_model=list[BidResponse])
async def list_bids(
    org: str | None = Query(default=None, description="기관명 부분일치"),
    category: str | None = Query(default=None),
    label: str | None = Query(default=None, description="relevant|irrelevant|watch|none"),
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    repo = BidRepository(session)
    return await repo.list_bids(
        organization=org, category=category, label=label, days=days, limit=limit
    )


@router.post("/collect", status_code=202)
async def trigger_collection():
    from src.main import run_daily_collection
    asyncio.create_task(run_daily_collection())
    return {"message": "수집 작업 시작됨"}
