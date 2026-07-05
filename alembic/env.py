"""Alembic sync env — autojebi 동기 SQLAlchemy 환경.

autojebi의 bid_pipeline 테이블은 SQLAlchemy Core (`Table()`)로 정의되어 있고
metadata 객체는 api/routers/notices.py에서 모듈 레벨로 생성된다. 그 metadata를
직접 import해서 target_metadata로 사용 — Base 클래스(ORM Declarative) 불필요.

abb 원본은 fully async였지만 autojebi는 동기 유지 결정 (M4 plan 4.x). 따라서
env.py도 sync로 작성하고 `engine_from_config` + 동기 `connect()`로 마이그레이션 실행.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from api.config import settings
from api.tables import metadata as target_metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# settings.database_url 런타임 대체 (시크릿은 .env 또는 컨테이너 env로만 전달)
if settings.database_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """offline 모드 — DBAPI 없이 SQL 스크립트 출력."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """online 모드 — 실제 DB 커넥션 + 트랜잭션."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
