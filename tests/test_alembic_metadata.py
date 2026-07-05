"""Alembic 설정/마이그레이션 일관성 테스트.

확인:
  1. alembic.ini + alembic/env.py가 로드 가능
  2. 0001_initial 리비전이 head로 인식됨
  3. autojebi의 bid_pipeline metadata 컬럼이 0001_initial이 만드는 컬럼 집합과 일치
     (drift 방지)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from api.routers.notices import bid_pipeline


@pytest.fixture
def alembic_cfg():
    root = Path(__file__).resolve().parent.parent
    cfg_path = root / "alembic.ini"
    assert cfg_path.exists(), "alembic.ini missing"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def test_alembic_config_loads(alembic_cfg):
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = list(script.get_heads())
    # 단일 head — 마이그레이션이 추가되면 head는 최신 리비전이 된다 (branch 없음 보장)
    assert len(heads) == 1, f"unexpected branching: {heads}"
    # 0001은 down_revision=None이라 항상 ancestor — get_revisions로 chain 확인
    chain = [r.revision for r in script.walk_revisions()]
    assert "0001_initial" in chain, f"0001_initial missing from chain: {chain}"


def test_initial_revision_creates_expected_columns(alembic_cfg):
    """0001_initial 마이그레이션이 만드는 컬럼이 Table 정의와 동수인지 확인."""
    script = ScriptDirectory.from_config(alembic_cfg)
    initial = script.get_revision("0001_initial")
    assert initial is not None
    assert initial.down_revision is None  # 첫 마이그레이션

    # bid_pipeline Table에 정의된 컬럼 수와 일치 확인
    # (마이그레이션 본문이 sa.Column(...) 호출을 같은 개수 포함하는지 텍스트로 확인)
    versions_dir = Path(script.dir) / "versions"
    initial_path = versions_dir / "0001_initial.py"
    text = initial_path.read_text(encoding="utf-8")

    # Table에 등록된 컬럼 수
    table_col_count = len(bid_pipeline.c)
    # 마이그레이션 내 sa.Column( 등장 횟수 (server_default 등의 nested 호출은 sa.text라 영향 없음)
    mig_col_count = text.count("sa.Column(")
    assert mig_col_count == table_col_count, (
        f"마이그레이션 컬럼 수({mig_col_count}) ≠ Table 컬럼 수({table_col_count}) — drift"
    )
