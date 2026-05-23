import uuid
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from src.common.timez import utcnow
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.deps import require_api_key
from src.db.repository import get_session, AlertRuleRepository
from src.db.models import Bid
from src.api.schemas import (
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleResponse,
    BidResponse,
)

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.get("", response_model=list[AlertRuleResponse])
async def list_rules(session: AsyncSession = Depends(get_session)):
    repo = AlertRuleRepository(session)
    return await repo.list_all()


@router.post(
    "",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def create_rule(payload: AlertRuleCreate, session: AsyncSession = Depends(get_session)):
    repo = AlertRuleRepository(session)
    return await repo.create(payload.model_dump())


@router.get("/{rule_id}", response_model=AlertRuleResponse)
async def get_rule(rule_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = AlertRuleRepository(session)
    rule = await repo.get(rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    return rule


@router.put(
    "/{rule_id}",
    response_model=AlertRuleResponse,
    dependencies=[Depends(require_api_key)],
)
async def update_rule(
    rule_id: uuid.UUID,
    payload: AlertRuleUpdate,
    session: AsyncSession = Depends(get_session),
):
    repo = AlertRuleRepository(session)
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    rule = await repo.update(rule_id, data)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    return rule


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_api_key)],
)
async def delete_rule(rule_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = AlertRuleRepository(session)
    if not await repo.delete(rule_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")


@router.post("/{rule_id}/test", response_model=list[BidResponse])
async def test_rule(
    rule_id: uuid.UUID,
    hours: int = 24,
    session: AsyncSession = Depends(get_session),
):
    """직전 N시간 저장 공고에 룰을 적용한 매칭 미리보기. 실제 발송 없음."""
    repo = AlertRuleRepository(session)
    rule = await repo.get(rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")

    since = utcnow() - timedelta(hours=hours)
    result = await session.execute(
        select(Bid).where(Bid.created_at >= since).order_by(Bid.relevance_score.desc())
    )
    bids = list(result.scalars().all())
    matched = [b for b in bids if rule.matches(b)]
    matched = matched[: rule.max_per_run]
    return matched
