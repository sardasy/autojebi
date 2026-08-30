"""Add proposal agent workspace tables.

Revision ID: 0012_proposal_agent_workspace
Revises: 0011_required_documents
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0012_proposal_agent_workspace"
down_revision: str | None = "0011_required_documents"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "proposal_documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("file_name", sa.String(length=500)),
        sa.Column("file_path", sa.Text()),
        sa.Column("document_type", sa.String(length=100)),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("project_name", sa.String(length=500)),
        sa.Column("customer_name", sa.String(length=300)),
        sa.Column("checksum", sa.String(length=128)),
        sa.Column("indexing_status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("document_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "category IN ('proposal','report','certificate','product','company','performance','other')",
            name="proposal_documents_category_check",
        ),
        sa.CheckConstraint(
            "indexing_status IN ('pending','indexed','failed')",
            name="proposal_documents_indexing_status_check",
        ),
    )
    op.create_index("proposal_documents_category_idx", "proposal_documents", ["category"])
    op.create_index("proposal_documents_customer_idx", "proposal_documents", ["customer_name"])
    op.create_index("proposal_documents_checksum_idx", "proposal_documents", ["checksum"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("proposal_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("heading", sa.Text()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "chunk_index", name="document_chunks_document_index_unique"),
    )
    op.create_index("document_chunks_document_idx", "document_chunks", ["document_id"])

    op.create_table(
        "project_performances",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_name", sa.String(length=500), nullable=False),
        sa.Column("customer_name", sa.String(length=300)),
        sa.Column("contract_date", sa.Date()),
        sa.Column("completion_date", sa.Date()),
        sa.Column("contract_amount", sa.Numeric(18, 2)),
        sa.Column("project_type", sa.String(length=200)),
        sa.Column("technologies", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("products", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("description", sa.Text()),
        sa.Column(
            "evidence_document_id",
            sa.String(),
            sa.ForeignKey("proposal_documents.id", ondelete="SET NULL"),
        ),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("project_performances_verified_idx", "project_performances", ["verified"])
    op.create_index("project_performances_customer_idx", "project_performances", ["customer_name"])

    op.create_table(
        "notice_requirements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(length=300), nullable=False),
        sa.Column("requirement_type", sa.String(length=100), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("evaluation_score", sa.Numeric(6, 2)),
        sa.Column("source_page", sa.Integer()),
        sa.Column("extracted_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "notice_no",
            "requirement_type",
            "requirement_text",
            name="notice_requirements_notice_type_text_unique",
        ),
    )
    op.create_index("notice_requirements_notice_idx", "notice_requirements", ["notice_no"])
    op.create_index("notice_requirements_type_idx", "notice_requirements", ["requirement_type"])

    op.create_table(
        "requirement_evidences",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "requirement_id",
            sa.String(),
            sa.ForeignKey("notice_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", sa.String(), sa.ForeignKey("proposal_documents.id", ondelete="SET NULL")),
        sa.Column("chunk_id", sa.String(), sa.ForeignKey("document_chunks.id", ondelete="SET NULL")),
        sa.Column("performance_id", sa.String(), sa.ForeignKey("project_performances.id", ondelete="SET NULL")),
        sa.Column("evidence_type", sa.String(length=100), nullable=False),
        sa.Column("relevance_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("reasoning_summary", sa.Text()),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("requirement_evidences_requirement_idx", "requirement_evidences", ["requirement_id"])
    op.create_index("requirement_evidences_document_idx", "requirement_evidences", ["document_id"])

    op.create_table(
        "proposal_sections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_key", sa.String(length=200), nullable=False, server_default="proposal"),
        sa.Column("section_key", sa.String(length=200), nullable=False),
        sa.Column("section_title", sa.String(length=500), nullable=False),
        sa.Column("generated_content", sa.Text(), nullable=False),
        sa.Column("generation_status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("fact_check_status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("fact_check_notes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("human_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "generation_status IN ('draft','verified','rejected','approved')",
            name="proposal_sections_generation_status_check",
        ),
        sa.CheckConstraint(
            "fact_check_status IN ('pending','pass','warning','reject')",
            name="proposal_sections_fact_check_status_check",
        ),
        sa.UniqueConstraint(
            "notice_no",
            "section_key",
            "version",
            name="proposal_sections_notice_section_version_unique",
        ),
    )
    op.create_index("proposal_sections_notice_idx", "proposal_sections", ["notice_no"])


def downgrade() -> None:
    op.drop_index("proposal_sections_notice_idx", table_name="proposal_sections")
    op.drop_table("proposal_sections")
    op.drop_index("requirement_evidences_document_idx", table_name="requirement_evidences")
    op.drop_index("requirement_evidences_requirement_idx", table_name="requirement_evidences")
    op.drop_table("requirement_evidences")
    op.drop_index("notice_requirements_type_idx", table_name="notice_requirements")
    op.drop_index("notice_requirements_notice_idx", table_name="notice_requirements")
    op.drop_table("notice_requirements")
    op.drop_index("project_performances_customer_idx", table_name="project_performances")
    op.drop_index("project_performances_verified_idx", table_name="project_performances")
    op.drop_table("project_performances")
    op.drop_index("document_chunks_document_idx", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("proposal_documents_checksum_idx", table_name="proposal_documents")
    op.drop_index("proposal_documents_customer_idx", table_name="proposal_documents")
    op.drop_index("proposal_documents_category_idx", table_name="proposal_documents")
    op.drop_table("proposal_documents")
