"""Add HWP field mapping master tables.

Revision ID: 0009_hwp_field_mapping
Revises: 0008_export_quality_control
Create Date: 2026-06-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0009_hwp_field_mapping"
down_revision: str | None = "0008_export_quality_control"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_key", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("business_number", sa.String()),
        sa.Column("ceo_name", sa.String()),
        sa.Column("address", sa.Text()),
        sa.Column("profile_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("profile_key", name="company_profiles_profile_key_unique"),
    )
    op.create_index("company_profiles_active_idx", "company_profiles", ["active"])

    op.create_table(
        "hwp_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_key", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("template_path", sa.Text(), nullable=False),
        sa.Column("template_version", sa.String()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("template_key", name="hwp_templates_template_key_unique"),
        sa.CheckConstraint("kind IN ('bid_form','proposal')"),
    )
    op.create_index("hwp_templates_active_idx", "hwp_templates", ["active"])

    op.create_table(
        "document_field_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("hwp_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hwp_field_name", sa.String(), nullable=False),
        sa.Column("context_path", sa.String(), nullable=False),
        sa.Column("value_type", sa.String(), nullable=False, server_default="string"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_value", sa.Text()),
        sa.Column("transform", sa.String(), nullable=False, server_default="none"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "template_id",
            "hwp_field_name",
            name="document_field_mappings_template_field_unique",
        ),
        sa.CheckConstraint(
            "transform IN ('none','date_yyyy_mm_dd','number_comma','business_number_dash','strip','truncate_1000')",
            name="document_field_mappings_transform_check",
        ),
    )
    op.create_index(
        "document_field_mappings_template_idx",
        "document_field_mappings",
        ["template_id", "active", "sort_order"],
    )

    op.create_table(
        "hwp_generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("hwp_templates.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "export_id",
            sa.Integer(),
            sa.ForeignKey("notice_exports.id", ondelete="SET NULL"),
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("context_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("input_values", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("replaced", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("missing", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("remaining_placeholders", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("worker_raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_detail", sa.Text()),
        sa.Column("review_status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.Text()),
        sa.Column("reviewed_by", sa.String()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending','running','completed','failed')"),
        sa.CheckConstraint("review_status IN ('pending','approved','rejected')"),
    )
    op.create_index("hwp_generation_jobs_notice_idx", "hwp_generation_jobs", ["notice_no"])
    op.create_index("hwp_generation_jobs_review_idx", "hwp_generation_jobs", ["review_status"])


def downgrade() -> None:
    op.drop_index("hwp_generation_jobs_review_idx", table_name="hwp_generation_jobs")
    op.drop_index("hwp_generation_jobs_notice_idx", table_name="hwp_generation_jobs")
    op.drop_table("hwp_generation_jobs")
    op.drop_index("document_field_mappings_template_idx", table_name="document_field_mappings")
    op.drop_table("document_field_mappings")
    op.drop_index("hwp_templates_active_idx", table_name="hwp_templates")
    op.drop_table("hwp_templates")
    op.drop_index("company_profiles_active_idx", table_name="company_profiles")
    op.drop_table("company_profiles")
