"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-17 05:10:09.601994
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_entity", "audit_events", ["entity_type", "entity_id", "id"], unique=False)
    op.create_table(
        "datasets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("time_precision", sa.Text(), nullable=False),
        sa.Column("coverage_contract", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("authorized_use_note", sa.Text(), nullable=True),
        sa.Column("raw_manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_kind IN ('synthetic','csv')", name="ck_datasets_source_kind"),
        sa.CheckConstraint("time_precision IN ('day','timestamp','mixed')", name="ck_datasets_time_precision"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "graph_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("max_ingest_seq", sa.BigInteger(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("graph_version", sa.Text(), nullable=False),
        sa.Column("input_manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("nodes_count", sa.Integer(), nullable=False),
        sa.Column("edges_count", sa.Integer(), nullable=False),
        sa.Column("transactions_count", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("formations_count", sa.Integer(), nullable=False),
        sa.Column("is_partial", sa.Boolean(), nullable=False),
        sa.Column("partial_reasons", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column(
            "quarantined_results",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('published')", name="ck_snapshots_status"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "input_manifest_sha256", "config_sha256", name="uq_snapshots_identity"),
    )
    op.create_table(
        "import_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("accepted", sa.Integer(), nullable=False),
        sa.Column("duplicate", sa.Integer(), nullable=False),
        sa.Column("quarantined", sa.Integer(), nullable=False),
        sa.Column("rejected", sa.Integer(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("max_ingest_seq", sa.BigInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", sa.UUID(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name="ck_jobs_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempts"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["graph_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_analysis_jobs_claim", "analysis_jobs", ["status", "created_at"], unique=False)
    op.create_table(
        "formations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subject_account_id", sa.Text(), nullable=False),
        sa.Column("member_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("entry_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exit_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("detector_id", sa.Text(), nullable=False),
        sa.Column("detector_version", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.CheckConstraint("kind IN ('funnel','chain')", name="ck_formations_kind"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["graph_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_formations_snapshot_id"), "formations", ["snapshot_id"], unique=False)
    op.create_table(
        "transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ingest_seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("import_batch_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_transaction_id", sa.Text(), nullable=False),
        sa.Column("sender_account_id", sa.Text(), nullable=False),
        sa.Column("receiver_account_id", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.Numeric(precision=38, scale=0), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("time_precision", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("raw_record_hash", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(time_precision = 'timestamp' AND occurred_at IS NOT NULL) OR (time_precision = 'day' AND occurred_at IS NULL)",
            name="ck_transactions_precision_consistency",
        ),
        sa.CheckConstraint("status IN ('posted','reversed','cancelled')", name="ck_transactions_status"),
        sa.CheckConstraint("time_precision IN ('day','timestamp')", name="ck_transactions_precision"),
        sa.CheckConstraint("amount_minor > 0", name="ck_transactions_amount_positive"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "source_id", "source_transaction_id", name="uq_transactions_source"),
        sa.UniqueConstraint("ingest_seq"),
    )
    op.create_index("ix_transactions_dataset_day", "transactions", ["dataset_id", "observed_date"], unique=False)
    op.create_index("ix_transactions_receiver", "transactions", ["dataset_id", "receiver_account_id"], unique=False)
    op.create_index("ix_transactions_sender", "transactions", ["dataset_id", "sender_account_id"], unique=False)
    op.create_table(
        "evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("formation_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=False),
        sa.Column("account_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("detector_version", sa.Text(), nullable=False),
        sa.Column("provenance_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "kind IN ('transaction_fact','aggregate_fact','graph_fact','temporal_fact','statistical_fact','coverage_fact','counterevidence')",
            name="ck_evidence_kind",
        ),
        sa.ForeignKeyConstraint(["formation_id"], ["formations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["graph_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidence_formation_id"), "evidence", ["formation_id"], unique=False)
    op.create_table(
        "fraud_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("formation_id", sa.UUID(), nullable=False),
        sa.Column("family", sa.Text(), nullable=False),
        sa.Column("detector_id", sa.Text(), nullable=False),
        sa.Column("detector_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("strength", sa.Float(), nullable=True),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dependency_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('supported','possible_ambiguous','contradicted','unavailable')",
            name="ck_signals_status",
        ),
        sa.ForeignKeyConstraint(["formation_id"], ["formations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["graph_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fraud_signals_formation_id"), "fraud_signals", ["formation_id"], unique=False)
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("formation_id", sa.UUID(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("policy_sha256", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("band", sa.Text(), nullable=False),
        sa.Column("signal_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supported_families", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_families", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "(band = 'insufficient_evidence' AND priority IS NULL) OR (band <> 'insufficient_evidence' AND priority BETWEEN 0 AND 100)",
            name="ck_risk_priority_semantics",
        ),
        sa.CheckConstraint("band IN ('critical','high','medium','low','insufficient_evidence')", name="ck_risk_band"),
        sa.ForeignKeyConstraint(["formation_id"], ["formations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["graph_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("formation_id"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("formation_id", sa.UUID(), nullable=False),
        sa.Column("risk_assessment_id", sa.UUID(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open','in_case','closed')", name="ck_alerts_status"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["formation_id"], ["formations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["risk_assessment_id"], ["risk_assessments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["graph_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "fingerprint", name="uq_alerts_fingerprint"),
    )
    op.create_index("ix_alerts_dataset_status", "alerts", ["dataset_id", "status"], unique=False)
    op.create_table(
        "evidence_transactions",
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("evidence_id", "transaction_id"),
    )
    op.create_index(
        op.f("ix_evidence_transactions_transaction_id"),
        "evidence_transactions",
        ["transaction_id"],
        unique=False,
    )
    op.create_table(
        "cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("alert_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('new','investigating','escalated','dismissed','closed','reopened')",
            name="ck_cases_status",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_id"),
    )
    op.create_table(
        "case_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_case_notes_case_id"), "case_notes", ["case_id"], unique=False)

    # Audit events are append-only. Enforced in the database so no application path
    # (or ad-hoc SQL through the app role) can rewrite history. This is tamper-evident
    # within this database's governance, not cryptographic immutability.
    op.execute(
        """
        CREATE FUNCTION nexora_audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'audit_events is append-only (% rejected)', TG_OP USING ERRCODE = 'insufficient_privilege';
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION nexora_audit_append_only();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS nexora_audit_append_only();")
    op.drop_index(op.f("ix_case_notes_case_id"), table_name="case_notes")
    op.drop_table("case_notes")
    op.drop_table("cases")
    op.drop_index(op.f("ix_evidence_transactions_transaction_id"), table_name="evidence_transactions")
    op.drop_table("evidence_transactions")
    op.drop_index("ix_alerts_dataset_status", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("risk_assessments")
    op.drop_index(op.f("ix_fraud_signals_formation_id"), table_name="fraud_signals")
    op.drop_table("fraud_signals")
    op.drop_index(op.f("ix_evidence_formation_id"), table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_transactions_sender", table_name="transactions")
    op.drop_index("ix_transactions_receiver", table_name="transactions")
    op.drop_index("ix_transactions_dataset_day", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(op.f("ix_formations_snapshot_id"), table_name="formations")
    op.drop_table("formations")
    op.drop_index("ix_analysis_jobs_claim", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_table("import_batches")
    op.drop_table("graph_snapshots")
    op.drop_table("datasets")
    op.drop_index("ix_audit_entity", table_name="audit_events")
    op.drop_table("audit_events")
