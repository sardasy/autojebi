from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from api.db.tables import metadata

workspaces = Table(
    "notice_workspaces",
    metadata,
    Column("notice_no", String, ForeignKey("bid_pipeline.notice_no"), primary_key=True),
    Column("version", Integer, nullable=False, default=1),
    Column("decision", String(20), nullable=False, default="pending"),
    Column("inputs", JSON, nullable=False),
    Column("source_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version > 0", name="workspace_version_positive"),
    CheckConstraint(
        "decision IN ('pending','participate','hold','decline')", name="workspace_decision_check"
    ),
)

jobs = Table(
    "workspace_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("notice_no", String, ForeignKey("notice_workspaces.notice_no"), nullable=False),
    Column("kind", String(30), nullable=False),
    Column("input_version", Integer, nullable=False),
    Column("idempotency_key", String(100), nullable=False),
    Column("status", String(20), nullable=False),
    Column("quality", String(10)),
    Column("snapshot", JSON, nullable=False),
    Column("parameters", JSON, nullable=False),
    Column("result", JSON),
    Column("error", JSON),
    Column("claim_token", String(36)),
    Column("lease_until", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    UniqueConstraint("notice_no", "idempotency_key", name="workspace_job_idempotency"),
    CheckConstraint(
        "status IN ('queued','running','succeeded','failed','blocked')", name="workspace_job_status"
    ),
    CheckConstraint(
        "quality IS NULL OR quality IN ('normal','warning')", name="workspace_job_quality"
    ),
    Index("workspace_job_queue", "status", "created_at"),
)

reviews = Table(
    "workspace_reviews",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("notice_no", String, ForeignKey("notice_workspaces.notice_no"), nullable=False),
    Column("input_version", Integer, nullable=False),
    Column("job_id", String(36), ForeignKey("workspace_jobs.id")),
    Column("action", String(30), nullable=False),
    Column("note", Text, nullable=False),
    Column("details", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

budgets = Table(
    "workspace_llm_budgets",
    metadata,
    Column("notice_no", String, ForeignKey("notice_workspaces.notice_no"), primary_key=True),
    Column("input_version", Integer, primary_key=True),
    Column("calls", Integer, nullable=False),
    Column("input_key", String(64), nullable=True),
    CheckConstraint("calls >= 0 AND calls <= 2", name="workspace_llm_call_limit"),
    Index("workspace_llm_input_key", "notice_no", "input_key"),
)

company_assets = Table(
    "company_assets", metadata,
    Column("id", String(36), primary_key=True),
    Column("version", Integer, nullable=False),
    Column("details", JSON, nullable=False),
    Column("file", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version > 0", name="company_asset_version_positive"),
)

company_asset_events = Table(
    "company_asset_events", metadata,
    Column("id", String(36), primary_key=True),
    Column("asset_id", String(36), ForeignKey("company_assets.id"), nullable=False),
    Column("version", Integer, nullable=False),
    Column("details", JSON, nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("asset_id", "version", name="company_asset_event_version"),
)
