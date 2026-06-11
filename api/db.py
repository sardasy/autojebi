import os
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine


class MissingDatabaseUrl(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise MissingDatabaseUrl("DATABASE_URL is not set")
    return create_engine(database_url, pool_pre_ping=True)


def require_engine() -> Engine:
    """라우터용 헬퍼 — DB 미설정 시 HTTPException 500으로 변환.

    여러 라우터 모듈에서 동일 패턴을 복붙하지 않도록 공통화.
    """
    try:
        return get_engine()
    except MissingDatabaseUrl as e:
        raise HTTPException(status_code=500, detail=str(e))

