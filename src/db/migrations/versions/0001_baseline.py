"""baseline phase1 schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bids",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(200), nullable=False, unique=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("organization", sa.String(200)),
        sa.Column("category", sa.String(100)),
        sa.Column("estimated_price", sa.BigInteger()),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("announcement_date", sa.DateTime(timezone=True)),
        sa.Column("location", sa.String(200)),
        sa.Column("raw_content", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("specs_json", sa.JSON()),
        sa.Column("relevance_score", sa.Float()),
        sa.Column("status", sa.String(50), server_default="new", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "notification_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("bid_id", UUID(as_uuid=True), sa.ForeignKey("bids.id"), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(50), server_default="sent", nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_logs")
    op.drop_table("bids")
