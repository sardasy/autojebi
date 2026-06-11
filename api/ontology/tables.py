"""SQLAlchemy Core Table 정의 — 온톨로지 8 테이블.

`api.routers.notices.metadata`를 공유한다 — `notice_assertions.notice_no`와
`notice_work_tasks.notice_no`가 `bid_pipeline.notice_no`를 FK로 참조하므로
같은 MetaData에 있어야 SQLAlchemy가 FK를 해결할 수 있다.

타입 전략:
  - JSON (SQLite/Postgres 호환). Postgres 운영에서는 alembic이 JSONB로 만들고,
    SQLAlchemy는 dialect-aware로 동일하게 read/write. SQLite는 JSON 타입으로 폴백.
  - 컬럼·인덱스·UNIQUE 제약은 alembic 0003_ontology와 1:1 (drift 방지).

회귀 영향: 같은 metadata를 쓰므로 기존 `metadata.create_all(engine)` 호출 시
ontology 테이블도 함께 생성된다 (빈 채로). 기존 동작에 영향 없음.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from api.routers.notices import metadata  # 단일 MetaData 공유 (bid_pipeline 포함)


# 1. 핵심 어휘 — 개념 정의
ontology_concepts = Table(
    "ontology_concepts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("canonical_key", Text, nullable=False, unique=True),
    Column("kind", Text, nullable=False),
    Column("display_name_ko", Text, nullable=False),
    Column("display_name_en", Text),
    Column("definition", Text),
    Column("attributes", JSON, nullable=False, default=dict),
    Column("status", Text, nullable=False, default="active"),
    Column("version", Integer, nullable=False, default=1),
    Column("valid_from", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("valid_to", DateTime(timezone=True)),
    Column("external_system", Text),
    Column("external_code", Text),
    Column("external_version", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "kind IN ('requirement','document_type','task_type','role','product_category','qualification','standard','risk_type')"
    ),
    CheckConstraint("status IN ('active','deprecated','draft')"),
    Index("ontology_concepts_kind_idx", "kind"),
    Index("ontology_concepts_status_idx", "status"),
    Index("ontology_concepts_external_idx", "external_system", "external_code"),
)


# 2. 동의어
ontology_aliases = Table(
    "ontology_aliases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "concept_id",
        Integer,
        ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("alias_text", Text, nullable=False),
    Column("alias_type", Text, nullable=False),
    Column("language", Text, nullable=False, default="ko"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        "concept_id", "alias_text", "alias_type", name="ontology_aliases_unique"
    ),
    CheckConstraint("alias_type IN ('synonym','abbreviation','legacy','vendor')"),
    Index("ontology_aliases_concept_idx", "concept_id"),
    Index("ontology_aliases_text_idx", "alias_text"),
)


# 3. 규칙
ontology_rules = Table(
    "ontology_rules",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("rule_key", Text, nullable=False, unique=True),
    Column("description", Text),
    Column("condition", JSON, nullable=False, default=dict),
    Column("result", JSON, nullable=False, default=dict),
    Column("priority", Integer, nullable=False, default=100),
    Column("version", Integer, nullable=False, default=1),
    Column("active", Boolean, nullable=False, default=True),
    Column("valid_from", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("valid_to", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ontology_rules_active_priority_idx", "active", "priority"),
)


# 4. 근거
knowledge_evidence = Table(
    "knowledge_evidence",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_kind", Text, nullable=False),
    Column("source_locator", JSON, nullable=False, default=dict),
    Column("hash", Text),
    Column("content_excerpt", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "source_kind IN ('g2b_field','attachment','email','llm_extracted','manual')"
    ),
    Index("knowledge_evidence_source_kind_idx", "source_kind"),
    Index("knowledge_evidence_hash_idx", "hash"),
)


# 5. 관계
ontology_relations = Table(
    "ontology_relations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "subject_concept_id",
        Integer,
        ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("predicate", Text, nullable=False),
    Column(
        "object_concept_id",
        Integer,
        ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("status", Text, nullable=False, default="active"),
    Column("confidence", Numeric(4, 3), nullable=False, default=1.000),
    Column(
        "evidence_id",
        Integer,
        ForeignKey("knowledge_evidence.id", ondelete="SET NULL"),
    ),
    Column("version", Integer, nullable=False, default=1),
    Column("valid_from", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("valid_to", DateTime(timezone=True)),
    UniqueConstraint(
        "subject_concept_id",
        "predicate",
        "object_concept_id",
        "version",
        name="ontology_relations_unique",
    ),
    CheckConstraint(
        "predicate IN ('requires_document','triggers_task','assigned_role','depends_on','satisfies','conflicts_with')"
    ),
    CheckConstraint("status IN ('active','deprecated')"),
    Index("ontology_relations_subject_idx", "subject_concept_id", "predicate"),
    Index("ontology_relations_object_idx", "object_concept_id"),
)


# 6. 공고별 사실
notice_assertions = Table(
    "notice_assertions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "notice_no",
        Text,
        ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "concept_id",
        Integer,
        ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("attributes", JSON, nullable=False, default=dict),
    Column("confidence", Numeric(4, 3), nullable=False, default=1.000),
    Column("status", Text, nullable=False, default="candidate"),
    Column(
        "evidence_id",
        Integer,
        ForeignKey("knowledge_evidence.id", ondelete="SET NULL"),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('candidate','approved','rejected')"),
    Index("notice_assertions_notice_idx", "notice_no"),
    Index("notice_assertions_concept_idx", "concept_id"),
    Index("notice_assertions_status_idx", "status"),
)


# 7. 파생 작업
notice_work_tasks = Table(
    "notice_work_tasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "notice_no",
        Text,
        ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("kind", Text, nullable=False),
    Column(
        "role_concept_id",
        Integer,
        ForeignKey("ontology_concepts.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("status", Text, nullable=False, default="pending"),
    Column("due_at", DateTime(timezone=True)),
    Column("derived_from", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('pending','in_progress','done','blocked')"),
    Index("notice_work_tasks_notice_idx", "notice_no"),
    Index("notice_work_tasks_status_idx", "status"),
    Index("notice_work_tasks_role_idx", "role_concept_id"),
    Index("notice_work_tasks_due_idx", "due_at"),
)


# 8. 역할 ↔ 담당자 매핑 (개인명은 이 테이블에서만 저장)
role_bindings = Table(
    "role_bindings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "role_concept_id",
        Integer,
        ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("assignee", Text, nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("valid_to", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        "role_concept_id", "assignee", "valid_from", name="role_bindings_unique"
    ),
    Index("role_bindings_role_idx", "role_concept_id"),
    Index("role_bindings_role_valid_to_idx", "role_concept_id", "valid_to"),
)


__all__ = [
    "metadata",
    "ontology_concepts",
    "ontology_aliases",
    "ontology_rules",
    "knowledge_evidence",
    "ontology_relations",
    "notice_assertions",
    "notice_work_tasks",
    "role_bindings",
]
