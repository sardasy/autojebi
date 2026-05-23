"""cascade on notification_logs FKs + add deadline / alert_rules.enabled indexes

Revision ID: 0004_cascade_indexes
Revises: 0003_seed_default_rule
Create Date: 2026-05-24
"""
from typing import Sequence, Union
from alembic import op


revision: str = "0004_cascade_indexes"
down_revision: Union[str, None] = "0003_seed_default_rule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # notification_logs.bid_id → bids.id  (CASCADE on delete)
    op.drop_constraint("notification_logs_bid_id_fkey", "notification_logs", type_="foreignkey")
    op.create_foreign_key(
        "notification_logs_bid_id_fkey",
        "notification_logs", "bids",
        ["bid_id"], ["id"],
        ondelete="CASCADE",
    )

    # notification_logs.rule_id → alert_rules.id  (SET NULL on delete)
    op.drop_constraint("notification_logs_rule_id_fkey", "notification_logs", type_="foreignkey")
    op.create_foreign_key(
        "notification_logs_rule_id_fkey",
        "notification_logs", "alert_rules",
        ["rule_id"], ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_bids_deadline", "bids", ["deadline"])
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_alert_rules_enabled", table_name="alert_rules")
    op.drop_index("ix_bids_deadline", table_name="bids")

    op.drop_constraint("notification_logs_rule_id_fkey", "notification_logs", type_="foreignkey")
    op.create_foreign_key(
        "notification_logs_rule_id_fkey",
        "notification_logs", "alert_rules",
        ["rule_id"], ["id"],
    )

    op.drop_constraint("notification_logs_bid_id_fkey", "notification_logs", type_="foreignkey")
    op.create_foreign_key(
        "notification_logs_bid_id_fkey",
        "notification_logs", "bids",
        ["bid_id"], ["id"],
    )
