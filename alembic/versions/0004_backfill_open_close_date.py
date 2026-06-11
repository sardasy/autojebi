"""Backfill bid_pipeline.open_date / close_date from raw JSONB.

Revision ID: 0004_backfill_open_close_date
Revises: 0003_ontology
Create Date: 2026-06-09

Some existing collected G2B rows have NULL open_date / close_date because
G2BClient.parse_datetime previously did not handle the live
'YYYY-MM-DD HH:MM:SS' format stored in raw->>'bidNtceDt' and raw->>'bidClseDt'.

This migration reparses only NULL date columns from raw JSONB. The parser fix
itself lives in code. Downgrade is a no-op because the original values were
missing, not transformed from another reliable source.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_backfill_open_close_date"
down_revision: str | None = "0003_ontology"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE bid_pipeline
        SET open_date = (raw->>'bidNtceDt')::timestamp AT TIME ZONE 'Asia/Seoul'
        WHERE open_date IS NULL
          AND raw->>'bidNtceDt' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$';
        """
    )
    op.execute(
        """
        UPDATE bid_pipeline
        SET close_date = (raw->>'bidClseDt')::timestamp AT TIME ZONE 'Asia/Seoul'
        WHERE close_date IS NULL
          AND raw->>'bidClseDt' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$';
        """
    )


def downgrade() -> None:
    pass
