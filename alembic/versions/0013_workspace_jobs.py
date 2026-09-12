"""Independent workspaces, durable jobs, immutable review history."""

import sqlalchemy as sa

from alembic import op

revision = "0013_workspace_jobs"
down_revision = "0012_proposal_agent_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notice_workspaces",
        sa.Column(
            "notice_no", sa.String(), sa.ForeignKey("bid_pipeline.notice_no"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name="workspace_version_positive"),
        sa.CheckConstraint(
            "decision IN ('pending','participate','hold','decline')",
            name="workspace_decision_check",
        ),
    )
    op.create_table(
        "workspace_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "notice_no", sa.String(), sa.ForeignKey("notice_workspaces.notice_no"), nullable=False
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("input_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("quality", sa.String(10)),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.JSON()),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("notice_no", "idempotency_key", name="workspace_job_idempotency"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','blocked')",
            name="workspace_job_status",
        ),
        sa.CheckConstraint(
            "quality IS NULL OR quality IN ('normal','warning')", name="workspace_job_quality"
        ),
    )
    op.create_index("workspace_job_queue", "workspace_jobs", ["status", "created_at"])
    op.create_table(
        "workspace_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "notice_no", sa.String(), sa.ForeignKey("notice_workspaces.notice_no"), nullable=False
        ),
        sa.Column("input_version", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("workspace_jobs.id")),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspace_llm_budgets",
        sa.Column(
            "notice_no", sa.String(), sa.ForeignKey("notice_workspaces.notice_no"), primary_key=True
        ),
        sa.Column("input_version", sa.Integer(), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.CheckConstraint("calls >= 0 AND calls <= 2", name="workspace_llm_call_limit"),
    )


def downgrade() -> None:
    for name in (
        "workspace_llm_budgets",
        "workspace_reviews",
        "workspace_jobs",
        "notice_workspaces",
    ):
        op.drop_table(name)
