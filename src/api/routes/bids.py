import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import get_session, BidRepository
from src.api.schemas import BidResponse

router = APIRouter(tags=["bids"])


@router.get("/bids", response_model=list[BidResponse])
async def list_bids(session: AsyncSession = Depends(get_session)):
    repo = BidRepository(session)
    return await repo.get_today_top_bids(limit=20)


@router.post("/collect", status_code=202)
async def trigger_collection():
    from src.main import run_daily_collection
    asyncio.create_task(run_daily_collection())
    return {"message": "수집 작업 시작됨"}
