"""필요서류 자동확인 — notice_required_documents 마스터 테이블.

첨부문서에서 추출한 제출서류를 제출시점(submit_stage)·요구유형(requirement_type)별로
근거문장/페이지/신뢰도와 함께 정규화 저장한다. 사람이 checked로 최종 확인.

Revision ID: 0011_required_documents
Revises: 0010b_noop_placeholder
Create Date: 2026-06-25
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0011_required_documents"
down_revision: str | None = "0010b_noop_placeholder"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "notice_required_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_name", sa.Text(), nullable=False),
        sa.Column("requirement_type", sa.String(), nullable=False, server_default="required"),
        sa.Column("submit_stage", sa.String(), nullable=False, server_default="bid"),
        sa.Column("source_file", sa.Text()),
        sa.Column("evidence_text", sa.Text()),
        sa.Column("page_no", sa.Integer()),
        sa.Column("deadline", sa.String()),
        sa.Column("condition", sa.Text()),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0"),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("owner", sa.String()),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "notice_no", "doc_name", "submit_stage",
            name="notice_required_documents_unique",
        ),
        sa.CheckConstraint(
            "requirement_type IN ('required','conditional','winner_only','contract_stage','reference')",
            name="notice_required_documents_type_check",
        ),
        sa.CheckConstraint(
            "submit_stage IN ('bid','proposal','price','post_award','contract','delivery','conditional')",
            name="notice_required_documents_stage_check",
        ),
    )
    op.create_index(
        "notice_required_documents_notice_idx",
        "notice_required_documents",
        ["notice_no"],
    )
    op.create_index(
        "notice_required_documents_stage_idx",
        "notice_required_documents",
        ["notice_no", "submit_stage"],
    )


def downgrade() -> None:
    op.drop_index("notice_required_documents_stage_idx", table_name="notice_required_documents")
    op.drop_index("notice_required_documents_notice_idx", table_name="notice_required_documents")
    op.drop_table("notice_required_documents")
