"""Persist CSV replay reservations and enforce batch/dataset consistency."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM transactions t JOIN import_batches b ON b.id = t.import_batch_id
                WHERE t.dataset_id <> b.dataset_id
            ) THEN
                RAISE EXCEPTION 'CSV integrity migration refused: transaction and import batch dataset mismatch';
            END IF;
        END $$;
    """)
    op.create_unique_constraint("uq_import_batch_dataset", "import_batches", ["id", "dataset_id"])
    op.create_foreign_key(
        "fk_transactions_batch_dataset",
        "transactions",
        "import_batches",
        ["import_batch_id", "dataset_id"],
        ["id", "dataset_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("transactions_import_batch_id_fkey", "transactions", type_="foreignkey")
    op.create_table(
        "csv_import_requests",
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("request_key", sa.String(160), primary_key=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("csv_import_requests")
    op.create_foreign_key(
        "transactions_import_batch_id_fkey",
        "transactions",
        "import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("fk_transactions_batch_dataset", "transactions", type_="foreignkey")
    op.drop_constraint("uq_import_batch_dataset", "import_batches", type_="unique")
