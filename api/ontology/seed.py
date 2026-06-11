"""M14 — 초기 통제어휘 시드 (멱등 upsert).

대상:
  - product_category 8 (기존 api.models.notices.Category Literal과 1:1)
  - role 4 (sales / tech_sw / tech_power / unassigned)
  - role_bindings 3 (기존 api.services.routing.ROUTING 매핑)
  - document_type 9 (기존 api.services.document_automation._rule_checklist와 1:1)
  - requirement 4 (계획 문서 핵심 시나리오)
  - alias 12+

canonical_key 형식: `{kind}:{ascii_slug}` — URL/path 안전, 디버깅 용이.
한국어는 display_name_ko에만.

Stage 2/3에서 동일 함수를 재호출해 추가·교정. 멱등성 보장.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, select

from api.ontology.tables import (
    ontology_aliases,
    ontology_concepts,
    role_bindings,
)


@dataclass(slots=True)
class SeedConcept:
    canonical_key: str
    kind: str
    display_name_ko: str
    definition: str
    display_name_en: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    aliases: list[tuple[str, str]] = field(default_factory=list)  # (alias_text, alias_type)


# ── product_category 8 ────────────────────────────────────────────────
PRODUCT_CATEGORIES: list[SeedConcept] = [
    SeedConcept(
        canonical_key="product_category:hil",
        kind="product_category",
        display_name_ko="HIL",
        display_name_en="Hardware-in-the-Loop",
        definition="Typhoon HIL 등 전력전자 시뮬레이션 장비/시스템 카테고리.",
        aliases=[
            ("Hardware-in-the-Loop", "synonym"),
            ("하드웨어 인 더 루프", "synonym"),
            ("Typhoon HIL", "vendor"),
        ],
    ),
    SeedConcept(
        canonical_key="product_category:sw",
        kind="product_category",
        display_name_ko="SW",
        display_name_en="Software",
        definition="라이선스/구독 형태의 소프트웨어 단독 제공.",
        aliases=[("PLECS", "vendor")],
    ),
    SeedConcept(
        canonical_key="product_category:igbt",
        kind="product_category",
        display_name_ko="IGBT",
        display_name_en="IGBT",
        definition="IGBT 기반 전력반도체 모듈·시스템.",
        aliases=[("Insulated Gate Bipolar Transistor", "synonym")],
    ),
    SeedConcept(
        canonical_key="product_category:scr",
        kind="product_category",
        display_name_ko="SCR",
        display_name_en="SCR",
        definition="SCR/사이리스터 기반 전력 변환 장비.",
        aliases=[
            ("사이리스터", "synonym"),
            ("Silicon Controlled Rectifier", "synonym"),
        ],
    ),
    SeedConcept(
        canonical_key="product_category:passive",
        kind="product_category",
        display_name_ko="수동소자",
        display_name_en="Passive Component",
        definition="캐패시터·인덕터·저항기·퓨즈·부스바 등 수동 전력 소자.",
    ),
    SeedConcept(
        canonical_key="product_category:abb_equipment",
        kind="product_category",
        display_name_ko="ABB장비",
        display_name_en="ABB Equipment",
        definition="ABB 사 제조 차단기·변압기·스위치기어·UPS·인버터 등 산업장비.",
        aliases=[("ABB", "vendor")],
    ),
    SeedConcept(
        canonical_key="product_category:mixed",
        kind="product_category",
        display_name_ko="혼합",
        display_name_en="Mixed",
        definition="2개 이상 카테고리가 혼합된 발주.",
    ),
    SeedConcept(
        canonical_key="product_category:unrelated",
        kind="product_category",
        display_name_ko="비관련",
        display_name_en="Unrelated",
        definition="당사 영업 범위 외 공고.",
    ),
]

# ── role 4 ────────────────────────────────────────────────────────────
ROLES: list[SeedConcept] = [
    SeedConcept(
        canonical_key="role:sales",
        kind="role",
        display_name_ko="영업 담당",
        display_name_en="Sales",
        definition="공고 1차 분류·고객 응대·실적/면허 서류 확보.",
    ),
    SeedConcept(
        canonical_key="role:tech_sw",
        kind="role",
        display_name_ko="기술 SW",
        display_name_en="Tech SW",
        definition="HIL/SW 카테고리 기술 검토 및 규격대응표 작성.",
    ),
    SeedConcept(
        canonical_key="role:tech_power",
        kind="role",
        display_name_ko="기술 전력",
        display_name_en="Tech Power",
        definition="IGBT/SCR/수동소자/ABB장비 기술 검토.",
        aliases=[("전력팀", "legacy")],
    ),
    SeedConcept(
        canonical_key="role:unassigned",
        kind="role",
        display_name_ko="미배정",
        display_name_en="Unassigned",
        definition="라우팅 미정 상태 (sentinel).",
    ),
]

# ── role_bindings (기존 ROUTING 매핑 1차) ────────────────────────────
ROLE_BINDINGS_SEED: list[tuple[str, str]] = [
    ("role:tech_sw", "Sangjun"),
    ("role:tech_power", "이용문"),
    ("role:unassigned", "미배정"),
]

# ── document_type 9 ──────────────────────────────────────────────────
DOCUMENT_TYPES: list[SeedConcept] = [
    SeedConcept(
        canonical_key="document_type:bid_form",
        kind="document_type",
        display_name_ko="입찰참가신청서",
        definition="HWP autofill 대상 기본 입찰참가신청서.",
    ),
    SeedConcept(
        canonical_key="document_type:business_registration",
        kind="document_type",
        display_name_ko="사업자등록증",
        definition="회사 공통 제출 서류 — 사업자등록 증빙.",
    ),
    SeedConcept(
        canonical_key="document_type:corporate_seal",
        kind="document_type",
        display_name_ko="법인등기/인감 관련 서류",
        definition="법인 등기부등본·인감증명서·사용인감계 등.",
    ),
    SeedConcept(
        canonical_key="document_type:manufacturer_letter",
        kind="document_type",
        display_name_ko="제조사 공급확약서",
        definition="제조사가 발급하는 공급 권한·공급 확약 증빙.",
    ),
    SeedConcept(
        canonical_key="document_type:catalog",
        kind="document_type",
        display_name_ko="카탈로그/기술자료",
        definition="제품 사양·성능 카탈로그.",
    ),
    SeedConcept(
        canonical_key="document_type:technical_compliance",
        kind="document_type",
        display_name_ko="규격대응표",
        definition="공고 요구사양 vs 제안 사양 대응 매트릭스.",
    ),
    SeedConcept(
        canonical_key="document_type:performance_record",
        kind="document_type",
        display_name_ko="납품실적증명",
        definition="실적 요건 대응 — 과거 납품 실적 증명서.",
    ),
    SeedConcept(
        canonical_key="document_type:bid_bond",
        kind="document_type",
        display_name_ko="보증보험/입찰보증",
        definition="입찰보증금 증빙 (보증서·지급각서 등).",
        aliases=[("입찰보증금 지급각서", "synonym")],
    ),
    SeedConcept(
        canonical_key="document_type:license_certificate",
        kind="document_type",
        display_name_ko="자격/면허 증빙",
        definition="지역/면허/자격 제한 대응 증빙.",
    ),
]

# ── requirement 4 ────────────────────────────────────────────────────
REQUIREMENTS: list[SeedConcept] = [
    SeedConcept(
        canonical_key="requirement:region_limit",
        kind="requirement",
        display_name_ko="지역제한 요건",
        definition="공고의 지역 참가 제한 (예: 본사 소재지 한정).",
    ),
    SeedConcept(
        canonical_key="requirement:license_required",
        kind="requirement",
        display_name_ko="면허 요건",
        definition="특정 면허·자격 보유 필수.",
    ),
    SeedConcept(
        canonical_key="requirement:performance_history",
        kind="requirement",
        display_name_ko="실적 요건",
        definition="일정 금액/건수 이상 납품 실적 필수.",
    ),
    SeedConcept(
        canonical_key="requirement:manufacturer_authorization",
        kind="requirement",
        display_name_ko="제조사 권한 요건",
        definition="제조사 공급확약·총판 권한 필수.",
    ),
]


ALL_CONCEPTS: list[SeedConcept] = (
    PRODUCT_CATEGORIES + ROLES + DOCUMENT_TYPES + REQUIREMENTS
)


class SeedReport(dict):
    """{concepts_inserted, concepts_updated, aliases_inserted, role_bindings_inserted}."""


def seed_ontology(engine: Engine, *, dry_run: bool = False) -> SeedReport:
    """초기 통제어휘를 멱등 upsert.

    재실행 시 동일 canonical_key는 (display_name_ko/definition/attributes 변경 시) UPDATE만,
    동일 alias (concept_id, alias_text, alias_type)는 SKIP, 동일 role_binding은 SKIP.

    dry_run=True 면 DB 변경 없이 SeedReport만 반환 (insertable counts).
    """
    report = SeedReport(
        concepts_inserted=0,
        concepts_updated=0,
        aliases_inserted=0,
        role_bindings_inserted=0,
    )

    with engine.begin() as conn:
        # 1단계: 개념 upsert
        concept_id_by_key: dict[str, int] = {}
        for sc in ALL_CONCEPTS:
            existing = conn.execute(
                select(
                    ontology_concepts.c.id,
                    ontology_concepts.c.display_name_ko,
                    ontology_concepts.c.display_name_en,
                    ontology_concepts.c.definition,
                    ontology_concepts.c.attributes,
                ).where(ontology_concepts.c.canonical_key == sc.canonical_key)
            ).first()

            if existing is None:
                if not dry_run:
                    res = conn.execute(
                        ontology_concepts.insert()
                        .values(
                            canonical_key=sc.canonical_key,
                            kind=sc.kind,
                            display_name_ko=sc.display_name_ko,
                            display_name_en=sc.display_name_en,
                            definition=sc.definition,
                            attributes=sc.attributes,
                        )
                        .returning(ontology_concepts.c.id)
                    )
                    concept_id_by_key[sc.canonical_key] = res.scalar_one()
                report["concepts_inserted"] += 1
            else:
                concept_id_by_key[sc.canonical_key] = existing.id
                changed = (
                    existing.display_name_ko != sc.display_name_ko
                    or existing.display_name_en != sc.display_name_en
                    or existing.definition != sc.definition
                    or dict(existing.attributes or {}) != sc.attributes
                )
                if changed:
                    if not dry_run:
                        conn.execute(
                            ontology_concepts.update()
                            .where(ontology_concepts.c.id == existing.id)
                            .values(
                                display_name_ko=sc.display_name_ko,
                                display_name_en=sc.display_name_en,
                                definition=sc.definition,
                                attributes=sc.attributes,
                            )
                        )
                    report["concepts_updated"] += 1

        # 2단계: alias upsert (concept_id가 있어야 하므로 dry_run에서 신규 concept은 스킵)
        for sc in ALL_CONCEPTS:
            cid = concept_id_by_key.get(sc.canonical_key)
            if cid is None:
                # dry_run + 신규 concept → alias 카운트만 미리 계산
                report["aliases_inserted"] += len(sc.aliases)
                continue
            for alias_text, alias_type in sc.aliases:
                existing = conn.execute(
                    select(ontology_aliases.c.id).where(
                        ontology_aliases.c.concept_id == cid,
                        ontology_aliases.c.alias_text == alias_text,
                        ontology_aliases.c.alias_type == alias_type,
                    )
                ).first()
                if existing is None:
                    if not dry_run:
                        conn.execute(
                            ontology_aliases.insert().values(
                                concept_id=cid,
                                alias_text=alias_text,
                                alias_type=alias_type,
                            )
                        )
                    report["aliases_inserted"] += 1

        # 3단계: role_bindings upsert
        for role_key, assignee in ROLE_BINDINGS_SEED:
            cid = concept_id_by_key.get(role_key)
            if cid is None:
                report["role_bindings_inserted"] += 1
                continue
            existing = conn.execute(
                select(role_bindings.c.id).where(
                    role_bindings.c.role_concept_id == cid,
                    role_bindings.c.assignee == assignee,
                )
            ).first()
            if existing is None:
                if not dry_run:
                    conn.execute(
                        role_bindings.insert().values(
                            role_concept_id=cid,
                            assignee=assignee,
                        )
                    )
                report["role_bindings_inserted"] += 1

        if dry_run:
            conn.rollback()

    return report
