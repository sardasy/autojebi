"""Alembic 0003_ontology 마이그레이션 일관성 테스트.

검증:
  1. 0003_ontology가 alembic chain에 포함되고 head는 최신 단일 revision.
  2. SQLAlchemy Core Table 정의(ontology.tables.metadata)가 인메모리 SQLite에
     create_all 가능 (FK·UNIQUE·인덱스 모두 정합).
  3. 모든 ontology_* 테이블이 생성되고 컬럼 수가 의도와 일치.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

# api.ontology.tables를 import해야 metadata에 ontology 테이블이 등록된다
import api.ontology.tables  # noqa: F401
from alembic.config import Config
from alembic.script import ScriptDirectory
from api.routers.notices import metadata


@pytest.fixture
def alembic_cfg():
    root = Path(__file__).resolve().parent.parent
    cfg_path = root / "alembic.ini"
    cfg = Config(str(cfg_path))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def test_alembic_chain_includes_0003_ontology(alembic_cfg):
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = list(script.get_heads())
    assert len(heads) == 1, f"unexpected branching: {heads}"
    assert heads[0] == "0010b_noop_placeholder", (
        f"expected 0010b as head, got {heads}"
    )
    chain = [r.revision for r in script.walk_revisions()]
    for rev in (
        "0001_initial",
        "0002_search_indexes",
        "0003_ontology",
        "0004_backfill_open_close_date",
        "0005_notice_spec_items",
        "0006_phase1_tracking",
        "0007_phase2_stabilization",
        "0008_export_quality_control",
        "0009_hwp_field_mapping",
        "0010_export_kind_bid_form_hwp",
        "0010b_noop_placeholder",
    ):
        assert rev in chain, f"{rev} missing from chain: {chain}"


def test_ontology_metadata_create_all_succeeds_on_sqlite():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 단일 metadata에 bid_pipeline + ontology 8개가 모두 등록돼 있다
    metadata.create_all(engine)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    expected = {
        "ontology_concepts",
        "ontology_aliases",
        "ontology_rules",
        "knowledge_evidence",
        "ontology_relations",
        "notice_assertions",
        "notice_work_tasks",
        "role_bindings",
    }
    assert expected.issubset(table_names), f"missing: {expected - table_names}"


def test_ontology_concepts_has_expected_columns():
    expected_cols = {
        "id",
        "canonical_key",
        "kind",
        "display_name_ko",
        "display_name_en",
        "definition",
        "attributes",
        "status",
        "version",
        "valid_from",
        "valid_to",
        "external_system",
        "external_code",
        "external_version",
        "created_at",
        "updated_at",
    }
    from api.ontology.tables import ontology_concepts
    actual = {c.name for c in ontology_concepts.c}
    assert actual == expected_cols, f"diff: {actual ^ expected_cols}"


def test_notice_assertions_has_fk_to_bid_pipeline():
    """`notice_assertions.notice_no` → `bid_pipeline.notice_no` FK 확인."""
    from api.ontology.tables import notice_assertions
    fks = [fk for fk in notice_assertions.c.notice_no.foreign_keys]
    assert len(fks) == 1
    assert fks[0].column.table.name == "bid_pipeline"
