"""bid pricing 컬럼 + estimated_price BigInteger → Numeric(18,2) 변환

Revision ID: 0005_bid_pricing_fields
Revises: 0004_cascade_indexes
Create Date: 2026-05-24

PR 2: 룰엔진(src/bidding/) 입력으로 자주 조회되는 필드를 specs_json 에서 별도 컬럼으로 승격.
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0005_bid_pricing_fields"
down_revision: Union[str, None] = "0004_cascade_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) estimated_price 타입 변경 BigInteger → Numeric(18,2)
    op.alter_column(
        "bids",
        "estimated_price",
        type_=sa.Numeric(18, 2),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="estimated_price::numeric(18,2)",
    )

    # 2) 신규 컬럼
    op.add_column("bids", sa.Column("base_price", sa.Numeric(18, 2), nullable=True))
    op.add_column("bids", sa.Column("nakchal_lower_rate", sa.Numeric(6, 5), nullable=True))
    op.add_column("bids", sa.Column("tender_type", sa.String(32), nullable=True))
    op.add_column("bids", sa.Column("evaluation_method", sa.String(32), nullable=True))
    op.add_column("bids", sa.Column("product_classification_code", sa.String(16), nullable=True))
    op.add_column(
        "bids",
        sa.Column("requires_direct_manufacturing", sa.Boolean(),
                  server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "bids",
        sa.Column("accepts_distributor_loa", sa.Boolean(),
                  server_default=sa.false(), nullable=False),
    )
    op.add_column("bids", sa.Column("eligibility_weights", JSONB(), nullable=True))

    # 3) 인덱스
    op.create_index("ix_bids_tender_type", "bids", ["tender_type"])
    op.create_index("ix_bids_evaluation_method", "bids", ["evaluation_method"])
    op.create_index("ix_bids_product_classification_code", "bids", ["product_classification_code"])
    op.create_index("ix_bids_base_price", "bids", ["base_price"])


def downgrade() -> None:
    op.drop_index("ix_bids_base_price", table_name="bids")
    op.drop_index("ix_bids_product_classification_code", table_name="bids")
    op.drop_index("ix_bids_evaluation_method", table_name="bids")
    op.drop_index("ix_bids_tender_type", table_name="bids")

    op.drop_column("bids", "eligibility_weights")
    op.drop_column("bids", "accepts_distributor_loa")
    op.drop_column("bids", "requires_direct_manufacturing")
    op.drop_column("bids", "product_classification_code")
    op.drop_column("bids", "evaluation_method")
    op.drop_column("bids", "tender_type")
    op.drop_column("bids", "nakchal_lower_rate")
    op.drop_column("bids", "base_price")

    # estimated_price 복원 (Decimal → BigInteger, 소수점 절단)
    op.alter_column(
        "bids",
        "estimated_price",
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(18, 2),
        existing_nullable=True,
        postgresql_using="estimated_price::bigint",
    )
