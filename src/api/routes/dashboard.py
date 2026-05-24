from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.repository import get_session, DashboardRepository
from src.api.schemas import DashboardStats, TimeseriesPoint, AwardTrendPoint

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    days: int = Query(default=30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
):
    repo = DashboardRepository(session)
    return await repo.stats(days=days)


@router.get("/timeseries", response_model=list[TimeseriesPoint])
async def get_timeseries(
    days: int = Query(default=30, ge=1, le=365),
    metric: str = Query(default="count", pattern="^(count|avg_relevance|sum_price)$"),
    session: AsyncSession = Depends(get_session),
):
    repo = DashboardRepository(session)
    return await repo.timeseries(days=days, metric=metric)


@router.get("/award-trend", response_model=list[AwardTrendPoint])
async def get_award_trend(
    org: str | None = Query(default=None),
    months: int = Query(default=12, ge=1, le=60),
    session: AsyncSession = Depends(get_session),
):
    repo = DashboardRepository(session)
    return await repo.award_trend(org=org, months=months)
