"""Add Phase 2 attachment jobs and evidence fields.

Revision ID: 0007_phase2_stabilization
Revises: 0006_phase1_tracking
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_phase2_stabilization"
down_revision: str | None = "0006_phase1_tracking"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("notice_spec_items", sa.Column("source_text", sa.Text()))
    op.add_column("notice_spec_items", sa.Column("source_file_name", sa.String()))
    op.add_column("notice_spec_items", sa.Column("source_page", sa.String()))
    op.add_column(
        "notice_spec_items",
        sa.Column("review_priority", sa.String(), nullable=False, server_default="normal"),
    )
    op.create_check_constraint(
        "notice_spec_items_review_priority_check",
        "notice_spec_items",
        "review_priority IN ('normal','high')",
    )

    op.create_table(
        "attachment_fetch_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String()),
        sa.CheckConstraint("status IN ('pending','running','completed','completed_with_errors')"),
    )
    op.create_index("attachment_fetch_jobs_notice_idx", "attachment_fetch_jobs", ["notice_no"])

    op.create_table(
        "attachment_fetch_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("attachment_fetch_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("upload_id", sa.String()),
        sa.Column("error", sa.Text()),
        sa.Column("source_ref", sa.String(), nullable=False, server_default="g2b_attachment"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending','success','failed','skipped')"),
    )
    op.create_index("attachment_fetch_files_job_idx", "attachment_fetch_files", ["job_id"])
    op.create_index("attachment_fetch_files_notice_idx", "attachment_fetch_files", ["notice_no"])


def downgrade() -> None:
    op.drop_index("attachment_fetch_files_notice_idx", table_name="attachment_fetch_files")
    op.drop_index("attachment_fetch_files_job_idx", table_name="attachment_fetch_files")
    op.drop_table("attachment_fetch_files")

    op.drop_index("attachment_fetch_jobs_notice_idx", table_name="attachment_fetch_jobs")
    op.drop_table("attachment_fetch_jobs")

    op.drop_constraint(
        "notice_spec_items_review_priority_check",
        "notice_spec_items",
        type_="check",
    )
    op.drop_column("notice_spec_items", "review_priority")
    op.drop_column("notice_spec_items", "source_page")
    op.drop_column("notice_spec_items", "source_file_name")
    op.drop_column("notice_spec_items", "source_text")
