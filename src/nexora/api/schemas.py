"""Transport DTOs. IDs and money are strings on the wire (ADR-003); see docs/INTERFACES.md."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Money = str  # decimal string of integer minor units


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(Model):
    code: str
    message: str
    request_id: str | None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(Model):
    error: ErrorBody


class Snapshot(Model):
    id: str
    dataset_id: str
    computed_at: dt.datetime
    window_start: dt.date | None
    window_end: dt.date | None
    max_ingest_seq: int
    graph_version: str
    input_manifest_sha256: str
    config_sha256: str
    policy_version: str
    nodes_count: int
    edges_count: int
    transactions_count: int
    excluded_count: int
    formations_count: int
    is_partial: bool
    partial_reasons: list[str]
    quarantined_count: int


class Job(Model):
    id: str
    dataset_id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempt_count: int
    max_ingest_seq: int
    snapshot_id: str | None
    error_code: str | None
    error_summary: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class Dataset(Model):
    id: str
    name: str
    source_kind: Literal["synthetic", "csv"]
    description: str | None
    time_precision: Literal["day", "timestamp", "mixed"]
    coverage_contract: dict[str, Any]
    authorized_use_note: str | None
    raw_manifest_sha256: str | None
    created_at: dt.datetime
    transactions_count: int
    latest_snapshot: Snapshot | None
    latest_job: Job | None


class Page(Model):
    total: int
    limit: int
    offset: int


class DatasetPage(Page):
    items: list[Dataset]


class ImportIssue(Model):
    row_number: int
    code: str
    field: str | None
    message: str


class ImportReport(Model):
    processed: int
    accepted: int
    duplicated_identical: int
    quarantined: int
    rejected: int
    warning_count: int
    error_codes: dict[str, int]
    warning_codes: dict[str, int]
    examples: list[ImportIssue]
    content_sha256: str | None


class ImportResult(Model):
    dataset: Dataset
    batch_id: str
    report: ImportReport


class SyntheticDatasetRequest(Model):
    suite: str = Field(min_length=1, max_length=64)
    seed: int = Field(ge=0, le=2**31 - 1)
    precision: Literal["day", "timestamp"] = "day"


class LabSuite(Model):
    id: str
    description: str
    scenario_families: list[str]


class AnalysisJobRequest(Model):
    dataset_id: str
    idempotency_key: str | None = Field(default=None, max_length=200)


class Transaction(Model):
    id: str
    source_transaction_id: str
    sender_account_id: str
    receiver_account_id: str
    amount_minor: Money
    currency: str
    observed_date: dt.date
    occurred_at: dt.datetime | None
    time_precision: Literal["day", "timestamp"]
    status: Literal["posted", "reversed", "cancelled"]
    is_synthetic: bool
    ingested_at: dt.datetime


class TransactionPage(Page):
    items: list[Transaction]


class ReasonCode(Model):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class FormationSummary(Model):
    id: str
    kind: Literal["funnel", "chain", "fanout", "cycle"]
    currency: str
    subject_account_id: str
    member_count: int
    window_start: dt.date
    window_end: dt.date
    features: dict[str, Any]


class FormationDetail(FormationSummary):
    member_ids: list[str]
    entry_ids: list[str]
    exit_ids: list[str]
    limitations: list[str]
    detector_id: str
    detector_version: str


Band = Literal["critical", "high", "medium", "low", "insufficient_evidence"]


class Risk(Model):
    priority: int | None
    band: Band
    policy_version: str
    reason_codes: list[ReasonCode]
    supported_families: list[str]
    missing_families: list[str]


class RiskDetail(Risk):
    policy_sha256: str


class AlertSummary(Model):
    id: str
    dataset_id: str
    status: Literal["open", "in_case", "closed"]
    revision: int
    first_seen: dt.datetime
    last_seen: dt.datetime
    snapshot_id: str
    in_latest_snapshot: bool
    formation: FormationSummary
    risk: Risk
    coverage_limitations: list[str]
    temporal_status: str | None
    evidence_count: int
    transaction_count: int
    case_id: str | None
    case_status: str | None


class AlertPage(Page):
    items: list[AlertSummary]


class EvidenceItem(Model):
    id: str
    kind: str
    reason_code: str
    account_ids: list[str]
    observations: dict[str, Any]
    thresholds: dict[str, Any]
    limitations: list[str]
    detector_version: str
    provenance_hash: str
    transaction_ids: list[str]


class SignalItem(Model):
    id: str
    family: str
    detector_id: str
    detector_version: str
    status: Literal["supported", "possible_ambiguous", "contradicted", "unavailable"]
    strength: float | None
    limitations: list[str]
    dependency_tags: list[str]


class DataRequest(Model):
    type: str
    subject_ids: list[str]
    proposed_window: list[str] | None
    missing_dependency: str
    expected_resolution: str
    priority_heuristic: int


class Coverage(Model):
    limitations: list[str]
    subject_limitations: list[str]
    boundary_accounts: list[str]
    data_requests: list[DataRequest]


class AlertDetail(AlertSummary):
    formation: FormationDetail  # type: ignore[assignment]
    risk: RiskDetail  # type: ignore[assignment]
    coverage: Coverage
    signals: list[SignalItem]
    evidence: list[EvidenceItem]
    snapshot: Snapshot


class EvidenceChain(Model):
    formation_id: str
    evidence: list[EvidenceItem]
    transactions: list[Transaction]


class GraphNode(Model):
    account_id: str
    hop: int
    is_boundary: bool


class GraphEdge(Model):
    sender: str
    receiver: str
    currency: str
    amount_minor: Money
    n_transactions: int
    first_date: dt.date
    last_date: dt.date


class Neighborhood(Model):
    snapshot_id: str
    center: str
    found: bool
    depth: int
    truncated: bool
    limits: dict[str, int]
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class AccountFormation(Model):
    formation_id: str
    kind: str
    role: Literal["subject", "member", "exit"]
    band: Band
    priority: int | None
    temporal_status: str | None
    alert_id: str | None


class AccountSummary(Model):
    snapshot_id: str
    account_id: str
    found: bool
    is_boundary: bool
    outgoing_count: int
    outgoing_minor: Money
    distinct_receivers: int
    incoming_count: int
    incoming_minor: Money
    distinct_senders: int
    formations: list[AccountFormation]


CaseStatus = Literal["new", "investigating", "escalated", "dismissed", "closed", "reopened"]


class CaseNote(Model):
    id: str
    author: str
    body: str
    created_at: dt.datetime


class CaseBase(Model):
    id: str
    alert_id: str
    title: str
    status: CaseStatus
    assigned_to: str | None
    opened_at: dt.datetime
    closed_at: dt.datetime | None
    decision: str | None
    decision_reason: str | None
    version: int
    allowed_transitions: list[CaseStatus]


class Case(CaseBase):
    notes: list[CaseNote]


class CaseListItem(CaseBase):
    dataset_id: str
    band: Band
    priority: int | None


class CasePage(Page):
    items: list[CaseListItem]


class OpenCaseRequest(Model):
    alert_id: str


class DecisionRequest(Model):
    to_status: CaseStatus
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)


class NoteRequest(Model):
    body: str = Field(min_length=1, max_length=4000)


class AuditEvent(Model):
    id: int
    actor: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    request_id: str | None
    created_at: dt.datetime


class Overview(Model):
    dataset: Dataset
    open_alerts_by_band: dict[str, int]
    cases_by_status: dict[str, int]
    formations_by_kind: dict[str, int]
    temporal_status_counts: dict[str, int]


class Health(Model):
    status: Literal["ok", "degraded"]
    database: bool
    migration: str | None
    queue: dict[str, int]
    demo_mode: bool
    actor: str


# -- Evaluation (recorded synthetic benchmark runs; read-only) ------------------------------
# Metric values are ratios in [0, 1] or counts; ``None`` means undefined (zero denominator).


class BenchmarkRunRef(Model):
    label: str
    created_at: str
    code_commit: str | None
    splits: list[str]


class BenchmarkRunList(Model):
    latest: str | None
    runs: list[BenchmarkRunRef]


class Ci95(Model):
    precision: list[float] | None
    recall: list[float] | None
    f1: list[float] | None
    fpr: list[float] | None


class ScenarioMetrics(Model):
    tp: int
    fp: int
    fn: int
    tn: int
    precision: float | None
    recall: float | None
    f1: float | None
    fpr: float | None
    fnr: float | None
    ci95: Ci95


class AlertMetrics(Model):
    raised: int
    precision: float | None
    alerts_per_network: float | None
    background_alerts_per_network: float | None
    alerts_per_1000_transactions: float | None
    on_benign_scenarios: int
    on_background: int
    duplicates_of_detected_scenario: int


class QueuePoint(Model):
    k: int
    precision: float | None
    recall: float | None


class AccountMetrics(Model):
    precision: float | None
    recall: float | None
    fpr: float | None


class LatencyMetrics(Model):
    median: float | None
    p95: float | None
    max: float | None
    per_1000_transactions: float | None


class Abstentions(Model):
    on_suspicious: int
    on_benign: int


class FamilyRate(Model):
    family: str
    label: Literal["suspicious", "benign"]
    networks: int
    rate: float | None
    rate_kind: Literal["detection_rate", "false_positive_rate"]
    alerts_per_network: float


class MethodSplitResult(Model):
    split: str
    method: str
    scenario: ScenarioMetrics
    alerts: AlertMetrics
    queue: list[QueuePoint]
    accounts: AccountMetrics
    latency_ms: LatencyMetrics
    abstentions: Abstentions
    networks: int
    transactions: int
    by_family: list[FamilyRate]


class BenchmarkFamily(Model):
    name: str
    label: Literal["suspicious", "benign"]
    group: Literal["suspicious", "benign", "hard_negative"]
    description: str


class BenchmarkSplit(Model):
    split: str
    networks: int
    transactions: int
    suspicious: int
    benign: int
    data_manifest_sha256: str
    truth_sha256: str


class BenchmarkSuite(Model):
    benchmark_version: str
    master_seed: int
    networks_per_family: dict[str, int]
    families: list[BenchmarkFamily]
    splits: list[BenchmarkSplit]


class BenchmarkRunInfo(Model):
    created_at: str
    duration_s: float
    code_commit: str | None
    code_dirty: bool | None
    python: str | None
    networkx: str | None
    cpu: str | None
    cpu_count: int | None
    splits_evaluated: list[str]


class BenchmarkMethod(Model):
    name: str
    group: Literal["baseline", "nexora"]
    description: str
    config_sha256: str | None
    threshold: float | None


class TimeToDetection(Model):
    split: str
    method: str
    median_days: int | None
    max_days: int | None
    detected_networks: int
    undetected_networks: int
    transient_detections: int


class ExampleAlert(Model):
    kind: str
    band: str | None
    score: float | None
    reasons: list[str]


class ExampleNetwork(Model):
    network_id: str
    family: str
    variant: str
    difficulty: str
    expected: str
    reason: str
    alerts: list[ExampleAlert]


class ErrorExamples(Model):
    split: str
    method: str
    false_positive_count: int
    false_negative_count: int
    false_positives: list[ExampleNetwork]
    false_negatives: list[ExampleNetwork]
    false_positives_by_family: dict[str, int]
    false_negatives_by_family: dict[str, int]


class Experiment(Model):
    kind: Literal["ablation", "robustness"]
    name: str
    method: str
    description: str
    split: str
    scenario: ScenarioMetrics
    alerts_per_network: float | None
    precision_at_10: float | None
    changed: int
    transitions: dict[str, int]
    band_changes: dict[str, int]


class ScaleResult(Model):
    method: str
    networks_merged: int
    transactions: int
    accounts: int
    edges: int
    formations: int
    partial_reasons: list[str]
    wall_seconds: float
    note: str


class BenchmarkReport(Model):
    label: str
    disclaimer: str
    run: BenchmarkRunInfo
    suite: BenchmarkSuite
    evaluation_units: dict[str, str]
    matching_rule: str
    operating_points: dict[str, str]
    methods: list[BenchmarkMethod]
    results: list[MethodSplitResult]
    time_to_detection: list[TimeToDetection]
    examples: list[ErrorExamples]
    experiments: list[Experiment]
    scale: list[ScaleResult]
