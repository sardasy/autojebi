"""M14 — 시드 멱등성·한국어 정합성 테스트."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from api.ontology.seed import ALL_CONCEPTS, ROLE_BINDINGS_SEED, seed_ontology
from api.ontology.tables import (
    ontology_aliases,
    ontology_concepts,
    role_bindings,
)
from api.routers.notices import metadata


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(e)
    return e


def test_seed_inserts_expected_counts(engine):
    report = seed_ontology(engine)
    # 8 카테고리 + 4 역할 + 9 서류 + 4 요건 = 25
    assert report["concepts_inserted"] == 25
    assert report["concepts_updated"] == 0
    assert report["role_bindings_inserted"] == 3
    # alias 개수는 seed.py 상수와 동기
    expected_aliases = sum(len(sc.aliases) for sc in ALL_CONCEPTS)
    assert report["aliases_inserted"] == expected_aliases

    with engine.begin() as conn:
        total_concepts = conn.execute(
            select(ontology_concepts.c.id)
        ).all()
        assert len(total_concepts) == 25


def test_seed_is_idempotent(engine):
    seed_ontology(engine)
    second = seed_ontology(engine)
    assert second["concepts_inserted"] == 0
    assert second["concepts_updated"] == 0
    assert second["aliases_inserted"] == 0
    assert second["role_bindings_inserted"] == 0


def test_seed_canonical_key_format(engine):
    seed_ontology(engine)
    with engine.begin() as conn:
        rows = conn.execute(
            select(ontology_concepts.c.canonical_key, ontology_concepts.c.kind)
        ).all()
    for key, kind in rows:
        assert key.startswith(f"{kind}:"), f"canonical_key {key!r} 가 kind {kind!r}와 불일치"
        # ASCII 슬러그 확인 — 한국어는 key에 들어가면 안 됨
        slug = key.split(":", 1)[1]
        assert slug.isascii(), f"canonical_key {key!r} slug에 비-ASCII: {slug!r}"


def test_seed_korean_text_roundtrip(engine):
    """한국어 display_name_ko가 UTF-8로 깨지지 않고 정확히 저장·조회된다."""
    seed_ontology(engine)
    with engine.begin() as conn:
        passive = conn.execute(
            select(ontology_concepts.c.display_name_ko).where(
                ontology_concepts.c.canonical_key == "product_category:passive"
            )
        ).scalar_one()
        unassigned = conn.execute(
            select(ontology_concepts.c.display_name_ko).where(
                ontology_concepts.c.canonical_key == "role:unassigned"
            )
        ).scalar_one()
    assert passive == "수동소자"
    assert unassigned == "미배정"


def test_seed_role_bindings_match_routing(engine):
    """기존 api.services.routing.ROUTING 매핑이 role_bindings에 그대로 들어간다."""
    seed_ontology(engine)
    with engine.begin() as conn:
        # role:tech_sw 의 concept_id 조회 → binding의 assignee 확인
        concept_id = conn.execute(
            select(ontology_concepts.c.id).where(
                ontology_concepts.c.canonical_key == "role:tech_sw"
            )
        ).scalar_one()
        assignee = conn.execute(
            select(role_bindings.c.assignee).where(
                role_bindings.c.role_concept_id == concept_id
            )
        ).scalar_one()
    assert assignee == "Sangjun"

    # 모든 시드 binding이 정확히 들어갔는지
    with engine.begin() as conn:
        all_bindings = conn.execute(
            select(
                ontology_concepts.c.canonical_key,
                role_bindings.c.assignee,
            ).select_from(
                role_bindings.join(
                    ontology_concepts,
                    role_bindings.c.role_concept_id == ontology_concepts.c.id,
                )
            )
        ).all()
    pairs = {(r[0], r[1]) for r in all_bindings}
    for key, assignee in ROLE_BINDINGS_SEED:
        assert (key, assignee) in pairs, f"missing binding {key} → {assignee}"


def test_seed_aliases_include_synonyms(engine):
    """대표적인 alias가 잘 들어갔는지 (Hardware-in-the-Loop, 입찰보증금 지급각서 등)."""
    seed_ontology(engine)
    with engine.begin() as conn:
        # product_category:hil 의 alias 확인
        hil_id = conn.execute(
            select(ontology_concepts.c.id).where(
                ontology_concepts.c.canonical_key == "product_category:hil"
            )
        ).scalar_one()
        hil_aliases = {
            r.alias_text
            for r in conn.execute(
                select(ontology_aliases.c.alias_text).where(
                    ontology_aliases.c.concept_id == hil_id
                )
            ).all()
        }
    assert "Hardware-in-the-Loop" in hil_aliases
    assert "하드웨어 인 더 루프" in hil_aliases


def test_seed_update_propagates_to_existing(engine, monkeypatch):
    """시드 상수의 display_name_ko를 변경한 뒤 재시드 → UPDATE 발생, INSERT 0건."""
    seed_ontology(engine)

    # ALL_CONCEPTS의 첫 product_category 정의를 수정
    from api.ontology import seed as seed_mod

    original = seed_mod.PRODUCT_CATEGORIES[0]
    modified = seed_mod.SeedConcept(
        canonical_key=original.canonical_key,
        kind=original.kind,
        display_name_ko="HIL (수정됨)",
        display_name_en=original.display_name_en,
        definition=original.definition,
        attributes=original.attributes,
        aliases=original.aliases,
    )
    monkeypatch.setattr(
        seed_mod, "PRODUCT_CATEGORIES", [modified] + seed_mod.PRODUCT_CATEGORIES[1:]
    )
    monkeypatch.setattr(
        seed_mod,
        "ALL_CONCEPTS",
        seed_mod.PRODUCT_CATEGORIES + seed_mod.ROLES + seed_mod.DOCUMENT_TYPES + seed_mod.REQUIREMENTS,
    )

    report = seed_ontology(engine)
    assert report["concepts_inserted"] == 0
    assert report["concepts_updated"] == 1

    with engine.begin() as conn:
        updated = conn.execute(
            select(ontology_concepts.c.display_name_ko).where(
                ontology_concepts.c.canonical_key == "product_category:hil"
            )
        ).scalar_one()
    assert updated == "HIL (수정됨)"


def test_seed_dry_run_makes_no_changes(engine):
    report = seed_ontology(engine, dry_run=True)
    assert report["concepts_inserted"] == 25  # 보고는 정확히
    with engine.begin() as conn:
        count = conn.execute(select(ontology_concepts.c.id)).all()
    assert len(count) == 0, "dry_run 인데 실제 INSERT 발생"
