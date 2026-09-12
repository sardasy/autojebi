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

from api.routers.notices import metadata

specifications = Table(
    "workspace_specifications", metadata,
    Column("id", String(36), primary_key=True),
    Column("notice_no", String, ForeignKey("notice_workspaces.notice_no"), nullable=False),
    Column("requirement_id", String(100), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("input_version", Integer, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("validation", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("notice_no", "requirement_id", name="spec_requirement_unique"),
    CheckConstraint("revision > 0 AND input_version > 0", name="spec_versions_positive"),
)
spec_events = Table(
    "workspace_spec_events", metadata,
    Column("id", String(36), primary_key=True),
    Column("spec_id", String(36), ForeignKey("workspace_specifications.id"), nullable=False),
    Column("revision", Integer, nullable=False), Column("input_version", Integer, nullable=False),
    Column("payload", JSON, nullable=False), Column("validation", JSON, nullable=False),
    Column("note", Text, nullable=False), Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("spec_id", "revision", name="spec_event_revision_unique"),
)
generations = Table(
    "spec_index_generations", metadata,
    Column("id", String(36), primary_key=True),
    Column("notice_no", String, ForeignKey("notice_workspaces.notice_no"), nullable=False),
    Column("job_id", String(36), ForeignKey("workspace_jobs.id"), nullable=False),
    Column("input_version", Integer, nullable=False),
    Column("input_hash", String(64), nullable=False),
    Column("manifest", JSON, nullable=False), Column("stores", JSON, nullable=False),
    Column("status", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("retire_after", DateTime(timezone=True)),
    CheckConstraint("status IN ('building','ready','failed','retired')", name="spec_generation_status"),
)
active_indexes = Table(
    "spec_active_indexes", metadata,
    Column("notice_no", String, ForeignKey("notice_workspaces.notice_no"), primary_key=True),
    Column("generation_id", String(36), ForeignKey("spec_index_generations.id"), nullable=False),
)
chunks = Table(
    "spec_search_chunks", metadata,
    Column("generation_id", String(36), ForeignKey("spec_index_generations.id"), primary_key=True),
    Column("id", String(64), primary_key=True),
    Column("document_id", String(200), nullable=False),
    Column("document_sha256", String(64), nullable=False),
    Column("text_sha256", String(64), nullable=False),
    Column("quote", Text, nullable=False), Column("locator", String(500), nullable=False),
    Column("start", Integer, nullable=False), Column("end", Integer, nullable=False),
    Column("identifiers", JSON, nullable=False), Column("properties", JSON, nullable=False),
    Column("payload", JSON, nullable=False),
    Index("spec_chunk_document", "generation_id", "document_id"),
)
