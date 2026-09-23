"""Provider-neutral decision records and confidence routing result."""

import sqlalchemy as sa

from alembic import op

revision = "0018_decision_layer"
down_revision = "0017_spec_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notice_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "notice_no",
            sa.String(),
            sa.ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("engine_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(200), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("product_family", sa.String(100), nullable=False),
        sa.Column("product_family_confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("application", sa.String(100), nullable=False),
        sa.Column("application_confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("company_relevance", sa.String(50), nullable=False),
        sa.Column("company_relevance_confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("bid_priority", sa.String(50), nullable=False),
        sa.Column("bid_priority_confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("overall_confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("route", sa.String(30), nullable=False),
        sa.Column("probabilities", sa.JSON(), nullable=False),
        sa.Column("decision_payload", sa.JSON(), nullable=False),
        sa.Column("human_result", sa.JSON()),
        sa.Column("reviewed_by", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "notice_no",
            "input_hash",
            "engine_name",
            "model_version",
            "policy_version",
            name="notice_decisions_request_unique",
        ),
        sa.CheckConstraint(
            "route IN ('auto_process','llm_verify','human_review')",
            name="notice_decisions_route_check",
        ),
    )
    op.create_index(
        "notice_decisions_notice_created_idx",
        "notice_decisions",
        ["notice_no", "created_at"],
    )
    op.create_index(
        "notice_decisions_route_idx",
        "notice_decisions",
        ["route", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("notice_decisions_route_idx", table_name="notice_decisions")
    op.drop_index("notice_decisions_notice_created_idx", table_name="notice_decisions")
    op.drop_table("notice_decisions")
