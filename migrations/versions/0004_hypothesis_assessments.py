"""hypothesis_assessments: competing explanations per formation (hypotheses-v1)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17 20:00:00

Authored as revision 0003 on PR #3; renumbered to 0004 when integrated after PR #15, whose
0003 (users/sessions) was already applied to the deployed database. This revision had never been
applied anywhere outside test databases, so renumbering it rewrites no deployed history.
Additive only: one new table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hypothesis_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("formation_id", sa.Uuid(), nullable=False),
        sa.Column("registry_version", sa.Text(), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("hypotheses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unavailable_information", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('suspicious_explanation_favoured','benign_explanation_favoured','inconclusive',"
            "'insufficient_data')",
            name="ck_hypothesis_verdict",
        ),
        sa.ForeignKeyConstraint(["formation_id"], ["formations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["graph_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("formation_id"),
    )


def downgrade() -> None:
    # Refuses while published hypothesis assessments exist: analyses are immutable records.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM hypothesis_assessments) THEN "
        "RAISE EXCEPTION 'refusing to drop published hypothesis assessments'; END IF; END $$;"
    )
    op.drop_table("hypothesis_assessments")
