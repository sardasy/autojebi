"""phase2: awards, alert rules, feedback, org priors + bid extensions

Revision ID: 0002_phase2
Revises: 0001_baseline
Create Date: 2026-05-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "0002_phase2"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Bid 확장 컬럼
    op.add_column("bids", sa.Column("detail_url", sa.String(500)))
    op.add_column("bids", sa.Column("award_status", sa.String(30), server_default="open", nullable=False))
    op.add_column("bids", sa.Column("user_label", sa.String(20)))
    op.add_column("bids", sa.Column("user_label_at", sa.DateTime(timezone=True)))

    # 2) Bid 인덱스
    op.create_index("ix_bids_organization", "bids", ["organization"])
    op.create_index("ix_bids_category", "bids", ["category"])
    op.create_index(
        "ix_bids_source_announcement_date",
        "bids",
        ["source", "announcement_date"],
    )
    op.create_index("ix_bids_relevance_score", "bids", ["relevance_score"])

    # 3) alert_rules
    op.create_table(
        "alert_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("filter_organizations", JSONB()),
        sa.Column("filter_categories", JSONB()),
        sa.Column("filter_sources", JSONB()),
        sa.Column("filter_keywords", JSONB()),
        sa.Column("min_price", sa.BigInteger()),
        sa.Column("max_price", sa.BigInteger()),
        sa.Column("min_relevance", sa.Float(), server_default="0.6", nullable=False),
        sa.Column("channels", JSONB()),
        sa.Column("teams_webhook_url", sa.String(500)),
        sa.Column("email_recipients", JSONB()),
        sa.Column("max_per_run", sa.Integer(), server_default="10", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4) notification_logs.rule_id
    op.add_column(
        "notification_logs",
        sa.Column("rule_id", UUID(as_uuid=True), sa.ForeignKey("alert_rules.id"), nullable=True),
    )

    # 5) bid_awards
    op.create_table(
        "bid_awards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("bid_id", UUID(as_uuid=True), sa.ForeignKey("bids.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_award_id", sa.String(200), nullable=False, unique=True),
        sa.Column("source_bid_id", sa.String(200)),
        sa.Column("winner_name", sa.String(300)),
        sa.Column("winner_biz_no", sa.String(20)),
        sa.Column("award_price", sa.BigInteger()),
        sa.Column("award_date", sa.Date()),
        sa.Column("participant_count", sa.Integer()),
        sa.Column("award_ratio", sa.Float()),
        sa.Column("raw_json", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bid_awards_source_bid_id", "bid_awards", ["source_bid_id"])
    op.create_index("ix_bid_awards_award_date", "bid_awards", ["award_date"])

    # 6) bid_feedback
    op.create_table(
        "bid_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("bid_id", UUID(as_uuid=True), sa.ForeignKey("bids.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("reviewer", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("bid_id", "reviewer", name="uq_bid_feedback_bid_reviewer"),
    )

    # 7) org_priors
    op.create_table(
        "org_priors",
        sa.Column("organization", sa.String(200), primary_key=True),
        sa.Column("n_samples", sa.Integer(), server_default="0", nullable=False),
        sa.Column("p_relevant", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("org_priors")
    op.drop_table("bid_feedback")
    op.drop_index("ix_bid_awards_award_date", table_name="bid_awards")
    op.drop_index("ix_bid_awards_source_bid_id", table_name="bid_awards")
    op.drop_table("bid_awards")
    op.drop_column("notification_logs", "rule_id")
    op.drop_table("alert_rules")
    op.drop_index("ix_bids_relevance_score", table_name="bids")
    op.drop_index("ix_bids_source_announcement_date", table_name="bids")
    op.drop_index("ix_bids_category", table_name="bids")
    op.drop_index("ix_bids_organization", table_name="bids")
    op.drop_column("bids", "user_label_at")
    op.drop_column("bids", "user_label")
    op.drop_column("bids", "award_status")
    op.drop_column("bids", "detail_url")
