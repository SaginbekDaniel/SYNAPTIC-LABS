"""Durable CSV upload queue. Terminal jobs release staged file bytes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "csv_import_jobs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("tenant", sa.Text(), nullable=True),
        sa.Column("request_key", sa.String(160), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("boundary", postgresql.JSONB(), nullable=False),
        sa.Column("max_rows", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope", "request_key", name="uq_csv_import_job_request"),
        sa.CheckConstraint(
            "status IN ('accepted','processing','completed','failed','cancelled')", name="ck_csv_job_status"
        ),
    )
    op.create_index("ix_csv_import_jobs_claim", "csv_import_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM csv_import_jobs WHERE status IN ('accepted', 'processing')) THEN
                RAISE EXCEPTION 'cannot discard unfinished CSV imports';
            END IF;
        END; $$;
    """)
    op.drop_table("csv_import_jobs")
