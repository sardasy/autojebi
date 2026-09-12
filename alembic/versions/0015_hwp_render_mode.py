"""Preserve field templates and opt into structured proposal layouts."""
import sqlalchemy as sa

from alembic import op

revision = "0015_hwp_render_mode"
down_revision = "0014_workspace_llm_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hwp_templates", sa.Column("render_mode", sa.String(40), nullable=False, server_default="fields"))
    with op.batch_alter_table("hwp_templates") as batch:
        batch.create_check_constraint("hwp_template_render_mode", "render_mode IN ('fields','proposal_layout_v1')")


def downgrade() -> None:
    with op.batch_alter_table("hwp_templates") as batch:
        batch.drop_constraint("hwp_template_render_mode", type_="check")
        batch.drop_column("render_mode")
