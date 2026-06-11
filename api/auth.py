"""API key 인증 (M9).

FastAPI Header dependency로 X-API-Key 검증.
settings.auth_enabled=False (API_KEY env 미설정) 시 자동 우회 — 개발 환경 친화.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from api.config import settings


def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """X-API-Key 헤더 검증 의존성.

    - API_KEY env 빈값 → 인증 자동 비활성 (통과).
    - 헤더 없거나 값 불일치 → 403.
    """
    if not settings.auth_enabled:
        return
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or missing X-API-Key",
        )
