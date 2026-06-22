"""M14 — 온톨로지 읽기 전용 라우터 (Stage 1).

쓰기·승인·후보 워크플로우는 Stage 3에서. 현재는 시드 데이터·미래 채워질 사실/관계·작업을 조회만 한다.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, asc, func, or_, select

from api.auth import verify_api_key
from api.db import require_engine
from api.models.ontology import (
    Alias,
    AliasType,
    Assertion,
    Concept,
    ConceptKind,
    ConceptListResponse,
    Evidence,
    Relation,
    RelationPredicate,
    RoleBinding,
    Rule,
    WorkTask,
)
from api.ontology.tables import (
    knowledge_evidence,
    notice_assertions,
    notice_work_tasks,
    ontology_aliases,
    ontology_concepts,
    ontology_relations,
    ontology_rules,
    role_bindings,
)

router = APIRouter(
    prefix="/ontology",
    tags=["ontology"],
    dependencies=[Depends(verify_api_key)],
)


def _row_to_concept(row: Any) -> Concept:
    return Concept(
        id=row["id"],
        canonical_key=row["canonical_key"],
        kind=row["kind"],
        display_name_ko=row["display_name_ko"],
        display_name_en=row["display_name_en"],
        definition=row["definition"],
        attributes=row["attributes"] or {},
        status=row["status"],
        version=row["version"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        external_system=row["external_system"],
        external_code=row["external_code"],
        external_version=row["external_version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/concepts", response_model=ConceptListResponse)
def list_concepts(
    kind: ConceptKind | None = Query(default=None),
    q: str | None = Query(default=None, description="canonical_key/display_name_ko 부분일치"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ConceptListResponse:
    engine = require_engine()
    stmt = select(ontology_concepts)
    count_stmt = select(func.count()).select_from(ontology_concepts)

    where = []
    if kind is not None:
        where.append(ontology_concepts.c.kind == kind)
    if q:
        like = f"%{q}%"
        where.append(
            or_(
                ontology_concepts.c.canonical_key.like(like),
                ontology_concepts.c.display_name_ko.like(like),
            )
        )
    if where:
        stmt = stmt.where(and_(*where))
        count_stmt = count_stmt.where(and_(*where))

    stmt = stmt.order_by(asc(ontology_concepts.c.canonical_key))
    stmt = stmt.limit(page_size).offset((page - 1) * page_size)

    with engine.begin() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(stmt).mappings().all()

    items = [_row_to_concept(r) for r in rows]
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return ConceptListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/concepts/{canonical_key:path}", response_model=Concept)
def get_concept(canonical_key: str) -> Concept:
    engine = require_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(ontology_concepts).where(
                ontology_concepts.c.canonical_key == canonical_key
            )
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"concept {canonical_key} not found")
    return _row_to_concept(row)


@router.get("/aliases", response_model=list[Alias])
def list_aliases(
    concept_id: int = Query(..., description="필수 — 단일 concept의 alias만 조회"),
    alias_type: AliasType | None = Query(default=None),
) -> list[Alias]:
    engine = require_engine()
    stmt = select(ontology_aliases).where(
        ontology_aliases.c.concept_id == concept_id
    )
    if alias_type is not None:
        stmt = stmt.where(ontology_aliases.c.alias_type == alias_type)
    stmt = stmt.order_by(asc(ontology_aliases.c.alias_text))
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        Alias(
            id=r["id"],
            concept_id=r["concept_id"],
            alias_text=r["alias_text"],
            alias_type=r["alias_type"],
            language=r["language"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/relations", response_model=list[Relation])
def list_relations(
    subject_id: int | None = Query(default=None),
    object_id: int | None = Query(default=None),
    predicate: RelationPredicate | None = Query(default=None),
) -> list[Relation]:
    # 전체 스캔 방지 — 필터 최소 1개 필수
    if subject_id is None and object_id is None and predicate is None:
        raise HTTPException(
            status_code=422,
            detail="at least one filter (subject_id, object_id, predicate) is required",
        )
    engine = require_engine()
    stmt = select(ontology_relations)
    if subject_id is not None:
        stmt = stmt.where(ontology_relations.c.subject_concept_id == subject_id)
    if object_id is not None:
        stmt = stmt.where(ontology_relations.c.object_concept_id == object_id)
    if predicate is not None:
        stmt = stmt.where(ontology_relations.c.predicate == predicate)
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        Relation(
            id=r["id"],
            subject_concept_id=r["subject_concept_id"],
            predicate=r["predicate"],
            object_concept_id=r["object_concept_id"],
            status=r["status"],
            confidence=r["confidence"],
            evidence_id=r["evidence_id"],
            version=r["version"],
            valid_from=r["valid_from"],
            valid_to=r["valid_to"],
        )
        for r in rows
    ]


@router.get("/rules", response_model=list[Rule])
def list_rules(
    active: bool | None = Query(default=None),
    priority_min: int | None = Query(default=None),
) -> list[Rule]:
    engine = require_engine()
    stmt = select(ontology_rules)
    if active is not None:
        stmt = stmt.where(ontology_rules.c.active == active)
    if priority_min is not None:
        stmt = stmt.where(ontology_rules.c.priority >= priority_min)
    stmt = stmt.order_by(asc(ontology_rules.c.priority))
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        Rule(
            id=r["id"],
            rule_key=r["rule_key"],
            description=r["description"],
            condition=r["condition"] or {},
            result=r["result"] or {},
            priority=r["priority"],
            version=r["version"],
            active=r["active"],
            valid_from=r["valid_from"],
            valid_to=r["valid_to"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/evidence/{evidence_id}", response_model=Evidence)
def get_evidence(evidence_id: int) -> Evidence:
    engine = require_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(knowledge_evidence).where(knowledge_evidence.c.id == evidence_id)
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"evidence {evidence_id} not found")
    return Evidence(
        id=row["id"],
        source_kind=row["source_kind"],
        source_locator=row["source_locator"] or {},
        hash=row["hash"],
        content_excerpt=row["content_excerpt"],
        created_at=row["created_at"],
    )


@router.get("/role-bindings", response_model=list[RoleBinding])
def list_role_bindings(
    role_concept_id: int | None = Query(default=None),
    assignee: str | None = Query(default=None),
    active_at: datetime | None = Query(
        default=None,
        description="이 시각에 유효한 바인딩만 (valid_from <= active_at < valid_to)",
    ),
) -> list[RoleBinding]:
    engine = require_engine()
    stmt = select(role_bindings)
    if role_concept_id is not None:
        stmt = stmt.where(role_bindings.c.role_concept_id == role_concept_id)
    if assignee is not None:
        stmt = stmt.where(role_bindings.c.assignee == assignee)
    if active_at is not None:
        stmt = stmt.where(
            role_bindings.c.valid_from <= active_at,
            or_(
                role_bindings.c.valid_to.is_(None),
                role_bindings.c.valid_to > active_at,
            ),
        )
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [
        RoleBinding(
            id=r["id"],
            role_concept_id=r["role_concept_id"],
            assignee=r["assignee"],
            valid_from=r["valid_from"],
            valid_to=r["valid_to"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get(
    "/notices/{notice_no:path}/assertions", response_model=list[Assertion]
)
def list_notice_assertions(notice_no: str) -> list[Assertion]:
    engine = require_engine()
    with engine.begin() as conn:
        rows = (
            conn.execute(
                select(notice_assertions).where(
                    notice_assertions.c.notice_no == notice_no
                )
            )
            .mappings()
            .all()
        )
    return [
        Assertion(
            id=r["id"],
            notice_no=r["notice_no"],
            concept_id=r["concept_id"],
            attributes=r["attributes"] or {},
            confidence=r["confidence"],
            status=r["status"],
            evidence_id=r["evidence_id"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get(
    "/notices/{notice_no:path}/work-tasks", response_model=list[WorkTask]
)
def list_notice_work_tasks(notice_no: str) -> list[WorkTask]:
    engine = require_engine()
    with engine.begin() as conn:
        rows = (
            conn.execute(
                select(notice_work_tasks).where(
                    notice_work_tasks.c.notice_no == notice_no
                )
            )
            .mappings()
            .all()
        )
    return [
        WorkTask(
            id=r["id"],
            notice_no=r["notice_no"],
            kind=r["kind"],
            role_concept_id=r["role_concept_id"],
            status=r["status"],
            due_at=r["due_at"],
            derived_from=r["derived_from"] or {},
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
