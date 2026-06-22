"""Add notice_spec_items for specification item review.

Revision ID: 0005_notice_spec_items
Revises: 0004_backfill_open_close_date
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_notice_spec_items"
down_revision: str | None = "0004_backfill_open_close_date"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "notice_spec_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("required_value", sa.Text()),
        sa.Column("proposed_value", sa.Text()),
        sa.Column("unit", sa.String()),
        sa.Column("category", sa.String(), nullable=False, server_default="technical"),
        sa.Column("source", sa.String(), nullable=False, server_default="rule"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0"),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="candidate"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("notice_no", "item_key", name="notice_spec_items_notice_item_unique"),
        sa.CheckConstraint("status IN ('candidate','reviewed','matched','gap','ignored')"),
    )
    op.create_index("notice_spec_items_notice_idx", "notice_spec_items", ["notice_no"])
    op.create_index("notice_spec_items_status_idx", "notice_spec_items", ["status"])


def downgrade() -> None:
    op.drop_index("notice_spec_items_status_idx", table_name="notice_spec_items")
    op.drop_index("notice_spec_items_notice_idx", table_name="notice_spec_items")
    op.drop_table("notice_spec_items")
