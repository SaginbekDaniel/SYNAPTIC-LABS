"""users.role: viewer / analyst / admin (backlog B-011)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-23 07:00:00

Additive only. Every existing account becomes ``analyst``, which keeps exactly the permissions all
accounts had before roles existed; the server default does the backfill in the same statement.
Downgrade drops the column (roles are lost, nothing else).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.Text(), server_default="analyst", nullable=False))
    op.create_check_constraint("ck_users_role", "users", "role IN ('viewer','analyst','admin')")


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
