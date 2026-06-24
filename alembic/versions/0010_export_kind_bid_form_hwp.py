"""Allow bid_form_hwp in notice_exports.kind check constraint.

M14 added the ``bid_form_hwp`` export kind in the SQLAlchemy model
(api/routers/notices.py) and write path (``_build_bid_form_export``), but the
Postgres CHECK constraint created back in 0006 still only allowed
``('excel','hwp','proposal_hwp')``. The HWP put-fields success path was never
exercised live until the agent's ``/document/put-fields`` endpoint existed, so
the drift surfaced as an IntegrityError on ``notice_exports_kind_check``.

Revision ID: 0010_export_kind_bid_form_hwp
Revises: 0009_hwp_field_mapping
Create Date: 2026-06-25
"""

from __future__ import annotations

from alembic import op

revision: str = "0010_export_kind_bid_form_hwp"
down_revision: str | None = "0009_hwp_field_mapping"
branch_labels: str | None = None
depends_on: str | None = None

CONSTRAINT_NAME = "notice_exports_kind_check"
NEW_KINDS = "kind IN ('excel','hwp','bid_form_hwp','proposal_hwp')"
OLD_KINDS = "kind IN ('excel','hwp','proposal_hwp')"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "notice_exports", type_="check")
    op.create_check_constraint(CONSTRAINT_NAME, "notice_exports", NEW_KINDS)


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "notice_exports", type_="check")
    op.create_check_constraint(CONSTRAINT_NAME, "notice_exports", OLD_KINDS)
