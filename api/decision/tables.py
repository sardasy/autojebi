"""SQLAlchemy Core persistence model for immutable, provider-neutral decision records."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from api.db.tables import metadata

notice_decisions = Table(
    "notice_decisions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "notice_no",
        String,
        ForeignKey("bid_pipeline.notice_no", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("engine_name", String(100), nullable=False),
    Column("model_version", String(200), nullable=False),
    Column("policy_version", String(100), nullable=False),
    Column("input_hash", String(64), nullable=False),
    Column("product_family", String(100), nullable=False),
    Column("product_family_confidence", Numeric(5, 4), nullable=False),
    Column("application", String(100), nullable=False),
    Column("application_confidence", Numeric(5, 4), nullable=False),
    Column("company_relevance", String(50), nullable=False),
    Column("company_relevance_confidence", Numeric(5, 4), nullable=False),
    Column("bid_priority", String(50), nullable=False),
    Column("bid_priority_confidence", Numeric(5, 4), nullable=False),
    Column("overall_confidence", Numeric(5, 4), nullable=False),
    Column("route", String(30), nullable=False),
    Column("probabilities", JSON, nullable=False),
    Column("decision_payload", JSON, nullable=False),
    Column("human_result", JSON),
    Column("reviewed_by", Text),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        "notice_no",
        "input_hash",
        "engine_name",
        "model_version",
        "policy_version",
        name="notice_decisions_request_unique",
    ),
    CheckConstraint(
        "route IN ('auto_process','llm_verify','human_review')",
        name="notice_decisions_route_check",
    ),
    Index("notice_decisions_notice_created_idx", "notice_no", "created_at"),
    Index("notice_decisions_route_idx", "route", "created_at"),
)

__all__ = ["notice_decisions"]
