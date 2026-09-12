"""Versioned company asset metadata; original files stay immutable."""
import sqlalchemy as sa

from alembic import op

revision = "0016_company_assets"
down_revision = "0015_hwp_render_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("file", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="company_asset_version_positive"),
    )
    op.create_table(
        "company_asset_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(36), sa.ForeignKey("company_assets.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("details", sa.JSON, nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("asset_id", "version", name="company_asset_event_version"),
    )


def downgrade() -> None:
    op.drop_table("company_asset_events")
    op.drop_table("company_assets")
