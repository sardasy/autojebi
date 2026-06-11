"""M14 — 온톨로지 Pydantic 응답 모델 (Stage 1 읽기 전용 API용).

DB 컬럼과 1:1. 모든 timezone-aware datetime. 페이지네이션 패턴은 M13 NoticeSearchResponse 재사용.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

ConceptKind = Literal[
    "requirement",
    "document_type",
    "task_type",
    "role",
    "product_category",
    "qualification",
    "standard",
    "risk_type",
]

ConceptStatus = Literal["active", "deprecated", "draft"]
AliasType = Literal["synonym", "abbreviation", "legacy", "vendor"]
RelationPredicate = Literal[
    "requires_document",
    "triggers_task",
    "assigned_role",
    "depends_on",
    "satisfies",
    "conflicts_with",
]
RelationStatus = Literal["active", "deprecated"]
EvidenceSource = Literal["g2b_field", "attachment", "email", "llm_extracted", "manual"]
AssertionStatus = Literal["candidate", "approved", "rejected"]
TaskStatus = Literal["pending", "in_progress", "done", "blocked"]


class Concept(BaseModel):
    id: int
    canonical_key: str
    kind: ConceptKind
    display_name_ko: str
    display_name_en: str | None = None
    definition: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: ConceptStatus = "active"
    version: int = 1
    valid_from: datetime
    valid_to: datetime | None = None
    external_system: str | None = None
    external_code: str | None = None
    external_version: str | None = None
    created_at: datetime
    updated_at: datetime


class Alias(BaseModel):
    id: int
    concept_id: int
    alias_text: str
    alias_type: AliasType
    language: str = "ko"
    created_at: datetime


class Rule(BaseModel):
    id: int
    rule_key: str
    description: str | None = None
    condition: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    version: int = 1
    active: bool = True
    valid_from: datetime
    valid_to: datetime | None = None
    created_at: datetime
    updated_at: datetime


class Evidence(BaseModel):
    id: int
    source_kind: EvidenceSource
    source_locator: dict[str, Any] = Field(default_factory=dict)
    hash: str | None = None
    content_excerpt: str | None = None
    created_at: datetime


class Relation(BaseModel):
    id: int
    subject_concept_id: int
    predicate: RelationPredicate
    object_concept_id: int
    status: RelationStatus = "active"
    confidence: Decimal = Decimal("1.000")
    evidence_id: int | None = None
    version: int = 1
    valid_from: datetime
    valid_to: datetime | None = None


class Assertion(BaseModel):
    id: int
    notice_no: str
    concept_id: int
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal = Decimal("1.000")
    status: AssertionStatus = "candidate"
    evidence_id: int | None = None
    created_at: datetime


class WorkTask(BaseModel):
    id: int
    notice_no: str
    kind: str
    role_concept_id: int
    status: TaskStatus = "pending"
    due_at: datetime | None = None
    derived_from: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class RoleBinding(BaseModel):
    id: int
    role_concept_id: int
    assignee: str
    valid_from: datetime
    valid_to: datetime | None = None
    created_at: datetime


class ConceptListResponse(BaseModel):
    items: list[Concept]
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
