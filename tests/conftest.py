"""pytest 공통 설정.

- sys.path 설정으로 루트 import.
- 표준 fixture: `sqlite_engine`, `client` — in-memory SQLite + TestClient.
  새 테스트는 이를 import 없이 바로 받아 쓸 수 있다 (pytest 자동 주입).
  기존 테스트가 자체 fixture를 정의한 경우 그쪽이 우선 적용.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def sqlite_engine(monkeypatch):
    """In-memory SQLite + 모든 metadata create_all + `api.db.get_engine` monkeypatch.

    `api.routers.notices.metadata`에는 `bid_pipeline` + ontology 테이블 8개가 모두 등록돼 있다
    (api.ontology.tables가 같은 metadata를 공유). 따라서 1번의 create_all로 충분.
    """
    # api.ontology.tables가 metadata에 자기 테이블을 등록하도록 임포트 보장
    import api.ontology.tables  # noqa: F401
    from api.routers.notices import metadata

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    monkeypatch.setattr("api.db.get_engine", lambda: engine)
    return engine


@pytest.fixture
def client(sqlite_engine, monkeypatch):
    """FastAPI TestClient — 스케줄러·인증 비활성."""
    from fastapi.testclient import TestClient

    from api.config import settings
    from api.main import app

    monkeypatch.setattr(settings, "scheduler_enabled", False)
    monkeypatch.setattr(settings, "api_key", "")
    return TestClient(app)
