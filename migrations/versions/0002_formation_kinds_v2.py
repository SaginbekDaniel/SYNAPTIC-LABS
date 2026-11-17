"""formation kinds fan_out and cycle (detectors-v2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17 12:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_formations_kind", "formations", type_="check")
    op.create_check_constraint("ck_formations_kind", "formations", "kind IN ('funnel','chain','fan_out','cycle')")


def downgrade() -> None:
    # Refuses (CHECK violation) while v2 formations exist: published analyses are immutable
    # and are never silently deleted to make a downgrade succeed.
    op.drop_constraint("ck_formations_kind", "formations", type_="check")
    op.create_check_constraint("ck_formations_kind", "formations", "kind IN ('funnel','chain')")
