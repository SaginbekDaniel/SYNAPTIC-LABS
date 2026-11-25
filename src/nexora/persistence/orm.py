"""ORM models. The Alembic migration is the schema of record; ``alembic check`` must
report no drift between these declarations and the migrated database."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True)


def _now() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[uuid.UUID] = _uuid()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    tenant: Mapped[str | None] = mapped_column(Text, index=True)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    time_precision: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_contract: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    authorized_use_note: Mapped[str | None] = mapped_column(Text)
    raw_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[dt.datetime] = _now()
    __table_args__ = (
        CheckConstraint("time_precision IN ('day','timestamp','mixed')", name="ck_datasets_time_precision"),
        CheckConstraint("source_kind IN ('synthetic','csv')", name="ck_datasets_source_kind"),
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[uuid.UUID] = _uuid()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)
    file_name: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate: Mapped[int] = mapped_column(Integer, nullable=False)
    quarantined: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = _now()
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("id", "dataset_id", name="uq_import_batch_dataset"),)


class CsvImportRequest(Base):
    __tablename__ = "csv_import_requests"
    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    request_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[dt.datetime] = _now()


class CsvImportJob(Base):
    __tablename__ = "csv_import_jobs"
    id: Mapped[uuid.UUID] = _uuid()
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    tenant: Mapped[str | None] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    boundary: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    max_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    lease_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    __table_args__ = (
        UniqueConstraint("scope", "request_key", name="uq_csv_import_job_request"),
        CheckConstraint(
            "status IN ('accepted','processing','completed','failed','cancelled')", name="ck_csv_job_status"
        ),
        Index("ix_csv_import_jobs_claim", "status", "created_at"),
    )


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[uuid.UUID] = _uuid()
    ingest_seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)
    import_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_transaction_id: Mapped[str] = mapped_column(Text, nullable=False)
    sender_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    receiver_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Numeric(38, 0), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    occurred_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    observed_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    time_precision: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    raw_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[dt.datetime] = _now()
    __table_args__ = (
        UniqueConstraint("dataset_id", "source_id", "source_transaction_id", name="uq_transactions_source"),
        ForeignKeyConstraint(
            ("import_batch_id", "dataset_id"),
            ("import_batches.id", "import_batches.dataset_id"),
            name="fk_transactions_batch_dataset",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount_minor > 0", name="ck_transactions_amount_positive"),
        CheckConstraint("time_precision IN ('day','timestamp')", name="ck_transactions_precision"),
        CheckConstraint("status IN ('posted','reversed','cancelled')", name="ck_transactions_status"),
        CheckConstraint(
            "(time_precision = 'timestamp' AND occurred_at IS NOT NULL) OR "
            "(time_precision = 'day' AND occurred_at IS NULL)",
            name="ck_transactions_precision_consistency",
        ),
        Index("ix_transactions_dataset_day", "dataset_id", "observed_date"),
        Index("ix_transactions_sender", "dataset_id", "sender_account_id"),
        Index("ix_transactions_receiver", "dataset_id", "receiver_account_id"),
    )


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"
    id: Mapped[uuid.UUID] = _uuid()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    max_ingest_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_start: Mapped[dt.date | None] = mapped_column(Date)
    window_end: Mapped[dt.date | None] = mapped_column(Date)
    graph_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    nodes_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edges_count: Mapped[int] = mapped_column(Integer, nullable=False)
    transactions_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    formations_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False)
    partial_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    quarantined_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    computed_at: Mapped[dt.datetime] = _now()
    __table_args__ = (
        UniqueConstraint("dataset_id", "input_manifest_sha256", "config_sha256", name="uq_snapshots_identity"),
        CheckConstraint("status IN ('published')", name="ck_snapshots_status"),
    )


class Formation(Base):
    __tablename__ = "formations"
    id: Mapped[uuid.UUID] = _uuid()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subject_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    member_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    entry_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    exit_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    detector_id: Mapped[str] = mapped_column(Text, nullable=False)
    detector_version: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    window_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    __table_args__ = (CheckConstraint("kind IN ('funnel','chain','fan_out','cycle')", name="ck_formations_kind"),)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = _uuid()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    formation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("formations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    observations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    detector_version: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        CheckConstraint(
            "kind IN ('transaction_fact','aggregate_fact','graph_fact','temporal_fact','statistical_fact',"
            "'coverage_fact','counterevidence')",
            name="ck_evidence_kind",
        ),
    )


class EvidenceTransaction(Base):
    """Join table: the database itself guarantees every evidence reference resolves (EVID-001)."""

    __tablename__ = "evidence_transactions"
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"), primary_key=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), primary_key=True, index=True
    )


class FraudSignal(Base):
    __tablename__ = "fraud_signals"
    id: Mapped[uuid.UUID] = _uuid()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    formation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("formations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    family: Mapped[str] = mapped_column(Text, nullable=False)
    detector_id: Mapped[str] = mapped_column(Text, nullable=False)
    detector_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float | None] = mapped_column(Float)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    dependency_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "status IN ('supported','possible_ambiguous','contradicted','unavailable')",
            name="ck_signals_status",
        ),
    )


class RiskAssessmentRow(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[uuid.UUID] = _uuid()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    formation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("formations.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int | None] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(Text, nullable=False)
    signal_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    supported_families: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    missing_families: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason_codes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        CheckConstraint("band IN ('critical','high','medium','low','insufficient_evidence')", name="ck_risk_band"),
        CheckConstraint(
            "(band = 'insufficient_evidence' AND priority IS NULL) OR "
            "(band <> 'insufficient_evidence' AND priority BETWEEN 0 AND 100)",
            name="ck_risk_priority_semantics",
        ),
    )


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = _uuid()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("graph_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    formation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("formations.id", ondelete="RESTRICT"), nullable=False)
    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    first_seen: Mapped[dt.datetime] = _now()
    last_seen: Mapped[dt.datetime] = _now()
    __table_args__ = (
        UniqueConstraint("dataset_id", "fingerprint", name="uq_alerts_fingerprint"),
        CheckConstraint("status IN ('open','in_case','closed')", name="ck_alerts_status"),
        Index("ix_alerts_dataset_status", "dataset_id", "status"),
    )


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = _uuid()
    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[dt.datetime] = _now()
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(Text)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    __table_args__ = (
        CheckConstraint(
            "status IN ('new','investigating','escalated','dismissed','closed','reopened')",
            name="ck_cases_status",
        ),
    )


class CaseNote(Base):
    __tablename__ = "case_notes"
    id: Mapped[uuid.UUID] = _uuid()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False, index=True)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = _now()


class AuditEvent(Base):
    """Append-only: a database trigger rejects UPDATE and DELETE (see migration 0001)."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id", "id"),)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id: Mapped[uuid.UUID] = _uuid()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    max_ingest_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    analysis_configuration: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("graph_snapshots.id", ondelete="RESTRICT"))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name="ck_jobs_status"),
        CheckConstraint("attempt_count >= 0", name="ck_jobs_attempts"),
        Index("ix_analysis_jobs_claim", "status", "created_at"),
    )


class TransferAssessment(Base):
    __tablename__ = "transfer_assessments"
    id: Mapped[uuid.UUID] = _uuid()
    tenant: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    intent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assessment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = _now()
    __table_args__ = (UniqueConstraint("tenant", "owner", "intent_id", name="uq_transfer_intent_scope"),)


class TransferActionEvent(Base):
    __tablename__ = "transfer_action_events"
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transfer_assessments.id", ondelete="RESTRICT"), primary_key=True
    )
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str] = mapped_column(Text, nullable=False)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = _now()
