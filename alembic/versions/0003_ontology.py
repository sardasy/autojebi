"""M14 Stage 1 — ontology layer (concepts, aliases, relations, rules, evidence, assertions, work_tasks, role_bindings)

Revision ID: 0003_ontology
Revises: 0002_search_indexes
Create Date: 2026-06-06

전력전자 입찰업무 온톨로지 — Stage 1 기반 정비.
공고 요건→서류→작업→역할을 근거와 함께 표현하기 위한 8개 정규화 테이블.

스코프 (Stage 1):
  - 스키마만. 추론 엔진·UI·document_automation 백필은 후속.
  - 통제어휘 시드는 `python -m api.ontology seed`로 별도 실행 (멱등).
  - 후보 승인/폐기 워크플로우는 추론 엔진 도입 시점(Stage 3).

기존 운영 DB는 본 마이그레이션 직접 적용 가능. 신규 환경은 0001→0002→0003 순.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_ontology"
down_revision: str | None = "0002_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CONCEPT_KINDS = (
    "requirement",
    "document_type",
    "task_type",
    "role",
    "product_category",
    "qualification",
    "standard",
    "risk_type",
)
_CONCEPT_STATUSES = ("active", "deprecated", "draft")
_ALIAS_TYPES = ("synonym", "abbreviation", "legacy", "vendor")
_RELATION_PREDICATES = (
    "requires_document",
    "triggers_task",
    "assigned_role",
    "depends_on",
    "satisfies",
    "conflicts_with",
)
_RELATION_STATUSES = ("active", "deprecated")
_EVIDENCE_SOURCES = ("g2b_field", "attachment", "email", "llm_extracted", "manual")
_ASSERTION_STATUSES = ("candidate", "approved", "rejected")
_TASK_STATUSES = ("pending", "in_progress", "done", "blocked")


def _check_in(column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    """CHECK column IN (...) — Postgres ENUM 대신 사용 (값 추가 시 마이그레이션 부담 최소)."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} IN ({quoted})")


def upgrade() -> None:
    # ── 1. ontology_concepts ──────────────────────────────────────────────
    op.create_table(
        "ontology_concepts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("canonical_key", sa.Text(), nullable=False, unique=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("display_name_ko", sa.Text(), nullable=False),
        sa.Column("display_name_en", sa.Text()),
        sa.Column("definition", sa.Text()),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("external_system", sa.Text()),
        sa.Column("external_code", sa.Text()),
        sa.Column("external_version", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        _check_in("kind", _CONCEPT_KINDS),
        _check_in("status", _CONCEPT_STATUSES),
    )
    op.create_index("ontology_concepts_kind_idx", "ontology_concepts", ["kind"])
    op.create_index("ontology_concepts_status_idx", "ontology_concepts", ["status"])
    op.create_index(
        "ontology_concepts_external_idx",
        "ontology_concepts",
        ["external_system", "external_code"],
    )

    # ── 2. ontology_aliases ───────────────────────────────────────────────
    op.create_table(
        "ontology_aliases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "concept_id",
            sa.BigInteger(),
            sa.ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias_text", sa.Text(), nullable=False),
        sa.Column("alias_type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), server_default="ko", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "concept_id", "alias_text", "alias_type", name="ontology_aliases_unique"
        ),
        _check_in("alias_type", _ALIAS_TYPES),
    )
    op.create_index("ontology_aliases_concept_idx", "ontology_aliases", ["concept_id"])
    op.create_index("ontology_aliases_text_idx", "ontology_aliases", ["alias_text"])

    # ── 3. ontology_rules ─────────────────────────────────────────────────
    op.create_table(
        "ontology_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("rule_key", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column(
            "condition",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "result",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ontology_rules_active_priority_idx",
        "ontology_rules",
        ["active", "priority"],
    )

    # ── 4. knowledge_evidence ─────────────────────────────────────────────
    op.create_table(
        "knowledge_evidence",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column(
            "source_locator",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("hash", sa.Text()),
        sa.Column("content_excerpt", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        _check_in("source_kind", _EVIDENCE_SOURCES),
    )
    op.create_index(
        "knowledge_evidence_source_kind_idx", "knowledge_evidence", ["source_kind"]
    )
    op.create_index("knowledge_evidence_hash_idx", "knowledge_evidence", ["hash"])

    # ── 5. ontology_relations ─────────────────────────────────────────────
    op.create_table(
        "ontology_relations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "subject_concept_id",
            sa.BigInteger(),
            sa.ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("predicate", sa.Text(), nullable=False),
        sa.Column(
            "object_concept_id",
            sa.BigInteger(),
            sa.ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column(
            "confidence",
            sa.Numeric(4, 3),
            server_default=sa.text("1.000"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_evidence.id", ondelete="SET NULL"),
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "subject_concept_id",
            "predicate",
            "object_concept_id",
            "version",
            name="ontology_relations_unique",
        ),
        _check_in("predicate", _RELATION_PREDICATES),
        _check_in("status", _RELATION_STATUSES),
    )
    op.create_index(
        "ontology_relations_subject_idx",
        "ontology_relations",
        ["subject_concept_id", "predicate"],
    )
    op.create_index(
        "ontology_relations_object_idx",
        "ontology_relations",
        ["object_concept_id"],
    )

    # ── 6. notice_assertions ──────────────────────────────────────────────
    op.create_table(
        "notice_assertions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.Text(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            sa.BigInteger(),
            sa.ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attributes",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Numeric(4, 3),
            server_default=sa.text("1.000"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="candidate", nullable=False),
        sa.Column(
            "evidence_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_evidence.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        _check_in("status", _ASSERTION_STATUSES),
    )
    op.create_index(
        "notice_assertions_notice_idx", "notice_assertions", ["notice_no"]
    )
    op.create_index(
        "notice_assertions_concept_idx", "notice_assertions", ["concept_id"]
    )
    op.create_index("notice_assertions_status_idx", "notice_assertions", ["status"])

    # ── 7. notice_work_tasks ──────────────────────────────────────────────
    op.create_table(
        "notice_work_tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.Text(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "role_concept_id",
            sa.BigInteger(),
            sa.ForeignKey("ontology_concepts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column(
            "derived_from",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        _check_in("status", _TASK_STATUSES),
    )
    op.create_index("notice_work_tasks_notice_idx", "notice_work_tasks", ["notice_no"])
    op.create_index("notice_work_tasks_status_idx", "notice_work_tasks", ["status"])
    op.create_index(
        "notice_work_tasks_role_idx", "notice_work_tasks", ["role_concept_id"]
    )
    op.create_index("notice_work_tasks_due_idx", "notice_work_tasks", ["due_at"])

    # ── 8. role_bindings ──────────────────────────────────────────────────
    op.create_table(
        "role_bindings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "role_concept_id",
            sa.BigInteger(),
            sa.ForeignKey("ontology_concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assignee", sa.Text(), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "role_concept_id", "assignee", "valid_from", name="role_bindings_unique"
        ),
    )
    op.create_index("role_bindings_role_idx", "role_bindings", ["role_concept_id"])
    op.create_index(
        "role_bindings_role_valid_to_idx",
        "role_bindings",
        ["role_concept_id", "valid_to"],
    )

    # updated_at 자동 트리거 — 0001의 set_updated_at() 함수 재사용
    for table in ("ontology_concepts", "ontology_rules", "notice_work_tasks"):
        op.execute(
            f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON {table};"
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    # 트리거 → FK 의존 역순으로 테이블 드롭
    for table in ("ontology_concepts", "ontology_rules", "notice_work_tasks"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON {table};")

    op.drop_index("role_bindings_role_valid_to_idx", table_name="role_bindings")
    op.drop_index("role_bindings_role_idx", table_name="role_bindings")
    op.drop_table("role_bindings")

    op.drop_index("notice_work_tasks_due_idx", table_name="notice_work_tasks")
    op.drop_index("notice_work_tasks_role_idx", table_name="notice_work_tasks")
    op.drop_index("notice_work_tasks_status_idx", table_name="notice_work_tasks")
    op.drop_index("notice_work_tasks_notice_idx", table_name="notice_work_tasks")
    op.drop_table("notice_work_tasks")

    op.drop_index("notice_assertions_status_idx", table_name="notice_assertions")
    op.drop_index("notice_assertions_concept_idx", table_name="notice_assertions")
    op.drop_index("notice_assertions_notice_idx", table_name="notice_assertions")
    op.drop_table("notice_assertions")

    op.drop_index("ontology_relations_object_idx", table_name="ontology_relations")
    op.drop_index("ontology_relations_subject_idx", table_name="ontology_relations")
    op.drop_table("ontology_relations")

    op.drop_index("knowledge_evidence_hash_idx", table_name="knowledge_evidence")
    op.drop_index(
        "knowledge_evidence_source_kind_idx", table_name="knowledge_evidence"
    )
    op.drop_table("knowledge_evidence")

    op.drop_index("ontology_rules_active_priority_idx", table_name="ontology_rules")
    op.drop_table("ontology_rules")

    op.drop_index("ontology_aliases_text_idx", table_name="ontology_aliases")
    op.drop_index("ontology_aliases_concept_idx", table_name="ontology_aliases")
    op.drop_table("ontology_aliases")

    op.drop_index("ontology_concepts_external_idx", table_name="ontology_concepts")
    op.drop_index("ontology_concepts_status_idx", table_name="ontology_concepts")
    op.drop_index("ontology_concepts_kind_idx", table_name="ontology_concepts")
    op.drop_table("ontology_concepts")
