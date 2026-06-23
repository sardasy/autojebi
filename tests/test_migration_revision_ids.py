"""Alembic 리비전 ID 길이 회귀 가드.

alembic의 `alembic_version.version_num` 컬럼은 기본 varchar(32)다. 리비전 ID가
32자를 넘으면 PostgreSQL에서 `alembic upgrade` 시 StringDataRightTruncation으로
실패한다(SQLite는 길이를 강제하지 않아 단위 테스트로는 드러나지 않음).
이 테스트는 모든 리비전 ID가 32자 이하임을 보장해 0007 같은 결함의 재발을 막는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

# alembic_version.version_num 기본 컬럼 폭
MAX_REVISION_ID_LEN = 32


@pytest.fixture
def alembic_cfg():
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def test_all_revision_ids_fit_version_column(alembic_cfg):
    script = ScriptDirectory.from_config(alembic_cfg)
    too_long = {
        rev.revision: len(rev.revision)
        for rev in script.walk_revisions()
        if len(rev.revision) > MAX_REVISION_ID_LEN
    }
    assert not too_long, (
        f"리비전 ID가 alembic_version varchar({MAX_REVISION_ID_LEN})를 초과 — "
        f"PostgreSQL 마이그레이션이 깨집니다: {too_long}"
    )
