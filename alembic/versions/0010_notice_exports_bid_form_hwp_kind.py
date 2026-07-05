"""No-op placeholder (superseded by 0010_export_kind_bid_form_hwp).

This file originally held the notice_exports.kind constraint fix, but its
revision id (``0010_notice_exports_bid_form_hwp_kind``, 37 chars) exceeded the
alembic_version varchar(32) policy enforced by
tests/test_migration_revision_ids.py. The fix was moved to the shorter
``0010_export_kind_bid_form_hwp``. It is kept as an empty follow-on revision
to preserve a single linear head with no branch.

DO NOT DELETE: 배포된 DB의 alembic_version이 ``0010b_noop_placeholder``를
가리키고 있을 수 있고, 0011의 down_revision이 이 리비전을 참조한다.
파일을 지우면 해당 DB에서 alembic이 리비전을 찾지 못해 깨진다 — 영구 no-op 유지.

Revision ID: 0010b_noop_placeholder
Revises: 0010_export_kind_bid_form_hwp
Create Date: 2026-06-25
"""

from __future__ import annotations

revision: str = "0010b_noop_placeholder"
down_revision: str | None = "0010_export_kind_bid_form_hwp"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
