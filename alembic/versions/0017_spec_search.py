"""Versioned specifications and rebuildable search projections."""
import sqlalchemy as sa

from alembic import op

revision = "0017_spec_search"
down_revision = "0016_company_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("workspace_specifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("notice_no", sa.String, sa.ForeignKey("notice_workspaces.notice_no"), nullable=False),
        sa.Column("requirement_id", sa.String(100), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False), sa.Column("input_version", sa.Integer, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False), sa.Column("validation", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("notice_no", "requirement_id", name="spec_requirement_unique"),
        sa.CheckConstraint("revision > 0 AND input_version > 0", name="spec_versions_positive"))
    op.create_table("workspace_spec_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spec_id", sa.String(36), sa.ForeignKey("workspace_specifications.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False), sa.Column("input_version", sa.Integer, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False), sa.Column("validation", sa.JSON, nullable=False),
        sa.Column("note", sa.Text, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("spec_id", "revision", name="spec_event_revision_unique"))
    op.create_table("spec_index_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("notice_no", sa.String, sa.ForeignKey("notice_workspaces.notice_no"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("workspace_jobs.id"), nullable=False),
        sa.Column("input_version", sa.Integer, nullable=False), sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("manifest", sa.JSON, nullable=False), sa.Column("stores", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retire_after", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('building','ready','failed','retired')", name="spec_generation_status"))
    op.create_table("spec_active_indexes",
        sa.Column("notice_no", sa.String, sa.ForeignKey("notice_workspaces.notice_no"), primary_key=True),
        sa.Column("generation_id", sa.String(36), sa.ForeignKey("spec_index_generations.id"), nullable=False))
    op.create_table("spec_search_chunks",
        sa.Column("generation_id", sa.String(36), sa.ForeignKey("spec_index_generations.id"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("document_id", sa.String(200), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False), sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("quote", sa.Text, nullable=False), sa.Column("locator", sa.String(500), nullable=False),
        sa.Column("start", sa.Integer, nullable=False), sa.Column("end", sa.Integer, nullable=False),
        sa.Column("identifiers", sa.JSON, nullable=False), sa.Column("properties", sa.JSON, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False))
    op.create_index("spec_chunk_document", "spec_search_chunks", ["generation_id", "document_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE INDEX spec_chunk_lexical ON spec_search_chunks USING gin (to_tsvector('simple', COALESCE(payload->>'search_text', quote)))")
        op.execute("CREATE INDEX spec_chunk_identifiers ON spec_search_chunks USING gin ((identifiers::jsonb))")


def downgrade() -> None:
    for name in ("spec_search_chunks", "spec_active_indexes", "spec_index_generations", "workspace_spec_events", "workspace_specifications"):
        op.drop_table(name)
