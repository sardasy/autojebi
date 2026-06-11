"""수동 수집 트리거 — POST /collect.

스케줄러를 기다리지 않고 G2B에서 즉시 1회 수집한다.
foreground 실행 (수집은 수십 초~수 분 걸릴 수 있으니 운영에선 별 워커 권장).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import verify_api_key
from api.collector.pipeline import run_collection
from api.db import MissingDatabaseUrl, get_engine

router = APIRouter(
    prefix="/collect",
    tags=["collect"],
    dependencies=[Depends(verify_api_key)],
)


class CollectResult(BaseModel):
    fetched: int
    new: int
    skipped: int


@router.post("", response_model=CollectResult)
def trigger_collect(start: date | None = None, end: date | None = None) -> CollectResult:
    try:
        engine = get_engine()
    except MissingDatabaseUrl as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    stats = run_collection(engine, start=start, end=end)
    return CollectResult(**stats)
