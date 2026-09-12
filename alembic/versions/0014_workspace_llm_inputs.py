"""Identify semantic LLM inputs without discarding versioned usage history."""

import sqlalchemy as sa

from alembic import op

revision = "0014_workspace_llm_inputs"
down_revision = "0013_workspace_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy counters are reconciled under the workspace lock from job snapshots.
    op.add_column("workspace_llm_budgets", sa.Column("input_key", sa.String(64), nullable=True))
    op.create_index("workspace_llm_input_key", "workspace_llm_budgets", ["notice_no", "input_key"])


def downgrade() -> None:
    op.drop_index("workspace_llm_input_key", table_name="workspace_llm_budgets")
    op.drop_column("workspace_llm_budgets", "input_key")
