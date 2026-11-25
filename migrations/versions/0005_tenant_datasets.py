"""Attach datasets to verified tenants; keep legacy demo data unassigned."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("tenant", sa.Text(), nullable=True))
    op.create_index("ix_datasets_tenant", "datasets", ["tenant"])


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM datasets WHERE tenant IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot remove tenant isolation from assigned datasets';
            END IF;
        END; $$;
    """)
    op.drop_index("ix_datasets_tenant", table_name="datasets")
    op.drop_column("datasets", "tenant")
