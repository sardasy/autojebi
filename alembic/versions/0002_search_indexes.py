"""search indexes — M-search: lifecycle/조회 hot path 커버

Revision ID: 0002_search_indexes
Revises: 0001_initial
Create Date: 2026-06-04

추가 인덱스:
  - (close_date, updated_at DESC)   — 기본 정렬 (마감 임박 + 최근 변경)
  - category                         — 다중 선택 카테고리 필터
  - org_name                         — 기관명 부분 일치 시 prefix 매칭에 도움
  - assignee                         — 담당자 단일 필터

pg_trgm / JSONB GIN은 권한·운영 영향이 커서 이번 마이그레이션에서 제외 (필요 시 후속).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_search_indexes"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS bid_pipeline_close_updated_idx "
        "ON bid_pipeline (close_date, updated_at DESC)"
    )
    op.create_index(
        "bid_pipeline_category_idx", "bid_pipeline", ["category"], if_not_exists=True
    )
    op.create_index(
        "bid_pipeline_org_name_idx", "bid_pipeline", ["org_name"], if_not_exists=True
    )
    op.create_index(
        "bid_pipeline_assignee_idx", "bid_pipeline", ["assignee"], if_not_exists=True
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS bid_pipeline_assignee_idx")
    op.execute("DROP INDEX IF EXISTS bid_pipeline_org_name_idx")
    op.execute("DROP INDEX IF EXISTS bid_pipeline_category_idx")
    op.execute("DROP INDEX IF EXISTS bid_pipeline_close_updated_idx")
