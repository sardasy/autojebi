"""FastAPI shared dependencies."""
from fastapi import Header, HTTPException, status
from src.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Admin-scoped routes guard.

    ADMIN_API_KEY 가 미설정이면 모든 mutation 거부 — 빈 키로 우회 불가.
    헤더 일치 시 통과.
    """
    expected = settings.admin_api_key
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY not configured — admin endpoints disabled",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
