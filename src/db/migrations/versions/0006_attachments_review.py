"""bids 에 첨부 본문 + dual extraction conflicts + 검토 플래그 추가

Revision ID: 0006_attachments_review
Revises: 0005_bid_pricing_fields
Create Date: 2026-05-24

PR 3: HWP/PDF 첨부 파싱 + regex/LLM 교차검증 결과 저장.
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0006_attachments_review"
down_revision: Union[str, None] = "0005_bid_pricing_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bids", sa.Column("attachment_text", sa.Text(), nullable=True))
    op.add_column("bids", sa.Column("extraction_conflicts", JSONB(), nullable=True))
    op.add_column(
        "bids",
        sa.Column("needs_human_review", sa.Boolean(),
                  server_default=sa.false(), nullable=False),
    )
    op.create_index("ix_bids_needs_human_review", "bids", ["needs_human_review"])


def downgrade() -> None:
    op.drop_index("ix_bids_needs_human_review", table_name="bids")
    op.drop_column("bids", "needs_human_review")
    op.drop_column("bids", "extraction_conflicts")
    op.drop_column("bids", "attachment_text")
