"""Pin detector configuration and authorized context with each new analysis job."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("analysis_configuration", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM analysis_jobs WHERE analysis_configuration IS NOT NULL AND status IN ('queued', 'running')
            ) THEN
                RAISE EXCEPTION 'cannot discard the configuration of unfinished analysis jobs';
            END IF;
        END; $$;
    """)
    op.drop_column("analysis_jobs", "analysis_configuration")
