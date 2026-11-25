"""Persist immutable risk assessments and append-only sandbox acknowledgements."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transfer_assessments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("intent_id", sa.UUID(), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("intent", postgresql.JSONB(), nullable=False),
        sa.Column("assessment", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant", "owner", "intent_id", name="uq_transfer_intent_scope"),
    )
    op.create_table(
        "transfer_action_events",
        sa.Column(
            "assessment_id",
            sa.UUID(),
            sa.ForeignKey("transfer_assessments.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("action_id", sa.UUID(), primary_key=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=False),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("""
        CREATE TRIGGER transfer_actions_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON transfer_action_events
        FOR EACH STATEMENT EXECUTE FUNCTION nexora_audit_append_only()
    """)
    op.execute("""
        CREATE FUNCTION nexora_preserve_transfer_assessment() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (to_jsonb(OLD) - 'status') IS DISTINCT FROM (to_jsonb(NEW) - 'status') THEN
                RAISE EXCEPTION 'transfer assessment evidence and intent are immutable';
            END IF;
            RETURN NEW;
        END; $$;
    """)
    op.execute("""
        CREATE TRIGGER transfer_assessment_immutable BEFORE UPDATE ON transfer_assessments
        FOR EACH ROW EXECUTE FUNCTION nexora_preserve_transfer_assessment()
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM transfer_assessments) THEN
                RAISE EXCEPTION 'transfer assessment history must be preserved before downgrade';
            END IF;
        END; $$;
    """)
    op.drop_table("transfer_action_events")
    op.drop_table("transfer_assessments")
    op.execute("DROP FUNCTION nexora_preserve_transfer_assessment()")
