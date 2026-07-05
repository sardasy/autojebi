import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import Connection, Engine, create_engine


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


def db_conn() -> Iterator[Connection]:
    """FastAPI Depends용 요청 단위 트랜잭션 커넥션.

    주의 — 읽기 전용 엔드포인트 전용. 이 FastAPI 버전에서 yield 정리 코드(=커밋)는
    응답 전송 후 실행되어, 커밋 실패가 나도 클라이언트는 200을 받는다 (실측 확인).
    쓰기 엔드포인트는 핸들러 안에서 `require_engine()` + `engine.begin()`을 유지할 것.
    """
    engine = require_engine()  # 호출 시점 획득 — 테스트의 api.db.get_engine 패치 존중
    with engine.begin() as conn:
        yield conn


Conn = Annotated[Connection, Depends(db_conn)]

