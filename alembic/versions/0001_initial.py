"""initial schema — consolidates base + M1 collect + M3 grade

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-03

기존 db/ 폴더의 raw SQL 3개를 단일 alembic 마이그레이션으로 압축:
  - db/bid_pipeline_schema.sql      (베이스 11 컬럼, 3 인덱스, 트리거)
  - db/migrations/0001_collect_columns.sql  (M1 G2B 9 컬럼, 3 인덱스)
  - db/migrations/0002_grade_columns.sql    (M3 그레이딩 10 컬럼, 2 인덱스)

총 30 컬럼, 8 인덱스, 1 트리거.

기존 운영 DB가 raw SQL로 이미 적용된 경우 `alembic stamp head`로 현재 상태만
기록한다 (재실행 안 함). 신규 환경은 `alembic upgrade head` 한 줄.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bid_pipeline",
        # 베이스 (db/bid_pipeline_schema.sql)
        sa.Column("notice_no", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text()),
        sa.Column("source", sa.Text()),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("category", sa.Text(), server_default="비관련", nullable=False),
        sa.Column(
            "fit_score",
            sa.Integer(),
            sa.CheckConstraint("fit_score >= 0 AND fit_score <= 100"),
            server_default="0",
            nullable=False,
        ),
        sa.Column("assignee", sa.Text(), server_default="미배정", nullable=False),
        sa.Column(
            "analysis",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="collected", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        # M1 G2B 수집 (db/migrations/0001_collect_columns.sql)
        sa.Column("bid_no", sa.Text()),
        sa.Column("bid_seq", sa.Text()),
        sa.Column("bid_type", sa.Text()),
        sa.Column("org_code", sa.Text()),
        sa.Column("org_name", sa.Text()),
        sa.Column("base_price", sa.Numeric(18, 2)),
        sa.Column("open_date", sa.DateTime(timezone=True)),
        sa.Column("close_date", sa.DateTime(timezone=True)),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        # M3 그레이딩 (db/migrations/0002_grade_columns.sql)
        sa.Column("score_spec", sa.Numeric(4, 3)),
        sa.Column("score_qual", sa.Numeric(4, 3)),
        sa.Column("score_price", sa.Numeric(4, 3)),
        sa.Column("score_total", sa.Numeric(4, 3)),
        sa.Column("grade_reason", sa.Text()),
        sa.Column("risk_note", sa.Text()),
        sa.Column("top_sku", sa.Text()),
        sa.Column("top_sku_name", sa.Text()),
        sa.Column("sku_match_score", sa.Numeric(4, 3)),
        sa.Column("graded_at", sa.DateTime(timezone=True)),
    )

    op.create_index("bid_pipeline_status_idx", "bid_pipeline", ["status"])
    op.create_index("bid_pipeline_fit_score_idx", "bid_pipeline", ["fit_score"])
    op.create_index("bid_pipeline_updated_at_idx", "bid_pipeline", ["updated_at"])
    op.create_index("bid_pipeline_bid_type_idx", "bid_pipeline", ["bid_type"])
    op.create_index("bid_pipeline_org_code_idx", "bid_pipeline", ["org_code"])
    op.create_index("bid_pipeline_close_date_idx", "bid_pipeline", ["close_date"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS bid_pipeline_score_total_idx "
        "ON bid_pipeline (score_total DESC)"
    )
    op.create_index("bid_pipeline_top_sku_idx", "bid_pipeline", ["top_sku"])

    # updated_at 자동 트리거
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS bid_pipeline_set_updated_at ON bid_pipeline;
        """
    )
    op.execute(
        """
        CREATE TRIGGER bid_pipeline_set_updated_at
        BEFORE UPDATE ON bid_pipeline
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS bid_pipeline_set_updated_at ON bid_pipeline;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
    op.drop_index("bid_pipeline_top_sku_idx", table_name="bid_pipeline")
    op.execute("DROP INDEX IF EXISTS bid_pipeline_score_total_idx")
    op.drop_index("bid_pipeline_close_date_idx", table_name="bid_pipeline")
    op.drop_index("bid_pipeline_org_code_idx", table_name="bid_pipeline")
    op.drop_index("bid_pipeline_bid_type_idx", table_name="bid_pipeline")
    op.drop_index("bid_pipeline_updated_at_idx", table_name="bid_pipeline")
    op.drop_index("bid_pipeline_fit_score_idx", table_name="bid_pipeline")
    op.drop_index("bid_pipeline_status_idx", table_name="bid_pipeline")
    op.drop_table("bid_pipeline")
