"""Add Phase 3 export quality metadata.

Revision ID: 0008_export_quality_control
Revises: 0007_phase2_stabilization
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0008_export_quality_control"
down_revision: str | None = "0007_phase2_stabilization"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("notice_exports", sa.Column("version", sa.String()))
    op.add_column("notice_exports", sa.Column("template_version", sa.String()))
    op.add_column(
        "notice_exports",
        sa.Column("validation_status", sa.String(), nullable=False, server_default="passed"),
    )
    op.add_column(
        "notice_exports",
        sa.Column("validation_errors", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("notice_exports", sa.Column("file_size", sa.Integer()))
    op.add_column("notice_exports", sa.Column("sha256", sa.String()))
    op.create_check_constraint(
        "notice_exports_validation_status_check",
        "notice_exports",
        "validation_status IN ('passed','warning','failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "notice_exports_validation_status_check",
        "notice_exports",
        type_="check",
    )
    op.drop_column("notice_exports", "sha256")
    op.drop_column("notice_exports", "file_size")
    op.drop_column("notice_exports", "validation_errors")
    op.drop_column("notice_exports", "validation_status")
    op.drop_column("notice_exports", "template_version")
    op.drop_column("notice_exports", "version")
