"""allow fan-out and cycle formations (detectors-v2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17 07:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_formations_kind", "formations", type_="check")
    op.create_check_constraint("ck_formations_kind", "formations", "kind IN ('funnel','chain','fanout','cycle')")


def downgrade() -> None:
    # Published analysis is immutable and never rewritten: existing v2 formations stay, and the
    # v1 constraint is restored NOT VALID so it binds new rows without rejecting history.
    op.drop_constraint("ck_formations_kind", "formations", type_="check")
    op.execute("ALTER TABLE formations ADD CONSTRAINT ck_formations_kind CHECK (kind IN ('funnel','chain')) NOT VALID")
