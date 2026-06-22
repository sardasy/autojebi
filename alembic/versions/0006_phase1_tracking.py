"""Add Phase 1 tracking tables and spec review metadata.

Revision ID: 0006_phase1_tracking
Revises: 0005_notice_spec_items
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_phase1_tracking"
down_revision: str | None = "0005_notice_spec_items"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("notice_spec_items", sa.Column("note", sa.Text()))
    op.add_column("notice_spec_items", sa.Column("reviewed_by", sa.String()))
    op.add_column("notice_spec_items", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "notice_spec_items",
        sa.Column(
            "locked_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.create_table(
        "notice_exports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("draft_id", sa.String(), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('excel','hwp','proposal_hwp')"),
    )
    op.create_index("notice_exports_notice_idx", "notice_exports", ["notice_no"])
    op.create_index(
        "notice_exports_active_idx",
        "notice_exports",
        ["notice_no", "kind", "draft_id", "deleted_at"],
    )

    op.create_table(
        "notice_errors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="error"),
        sa.Column("source", sa.String(), nullable=False, server_default="system"),
        sa.Column("file_name", sa.String()),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("severity IN ('info','warning','error')"),
    )
    op.create_index("notice_errors_notice_idx", "notice_errors", ["notice_no"])
    op.create_index("notice_errors_unresolved_idx", "notice_errors", ["notice_no", "resolved_at"])


def downgrade() -> None:
    op.drop_index("notice_errors_unresolved_idx", table_name="notice_errors")
    op.drop_index("notice_errors_notice_idx", table_name="notice_errors")
    op.drop_table("notice_errors")

    op.drop_index("notice_exports_active_idx", table_name="notice_exports")
    op.drop_index("notice_exports_notice_idx", table_name="notice_exports")
    op.drop_table("notice_exports")

    op.drop_column("notice_spec_items", "locked_fields")
    op.drop_column("notice_spec_items", "reviewed_at")
    op.drop_column("notice_spec_items", "reviewed_by")
    op.drop_column("notice_spec_items", "note")
