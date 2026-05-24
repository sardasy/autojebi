"""seed default alert rule (preserves phase1 notification behavior)

Revision ID: 0003_seed_default_rule
Revises: 0002_phase2
Create Date: 2026-05-23
"""
import uuid
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op


revision: str = "0003_seed_default_rule"
down_revision: Union[str, None] = "0002_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_RULE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            INSERT INTO alert_rules
                (id, name, enabled, min_relevance, channels, max_per_run, created_at, updated_at)
            VALUES
                ('{DEFAULT_RULE_ID}'::uuid, 'default', TRUE, 0.6, '["teams","email"]'::jsonb, 10, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(f"DELETE FROM alert_rules WHERE id = '{DEFAULT_RULE_ID}'::uuid")
    )
