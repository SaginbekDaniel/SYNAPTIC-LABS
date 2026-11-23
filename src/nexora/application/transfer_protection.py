"""Deterministic, formative policy for simulated transfer intents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictBool, StrictStr, model_validator

from nexora.domain.analysis import Band, Family, FormationKind, SignalStatus
from nexora.domain.ids import canonical_json, sha256_hex, stable_uuid
from nexora.domain.transfers import ObservedTransfer

Decision = Literal["ALLOW", "WARN", "STEP_UP", "LIMITED_SIGNAL", "UNAVAILABLE"]
Coverage = Literal["SUFFICIENT", "LIMITED", "UNAVAILABLE"]
RiskBand = Literal["LOW", "ELEVATED", "HIGH", "UNKNOWN"]
Action = Literal["CONTINUE_SIMULATION", "CANCEL", "REVIEW_DETAILS", "CONTACT_OFFICIAL_SUPPORT", "RETRY"]
Limitation = Literal[
    "INSUFFICIENT_HISTORY", "INCOMPLETE_GRAPH", "AMBIGUOUS_TIMESTAMPS", "STALE_PROFILE", "MISSING_PROFILE"
]
Failure = Literal["DEPENDENCY_FAILURE", "TIMEOUT", "FEATURE_DISABLED"]
Reason = Literal[
    Limitation,
    Failure,
    "NO_SUPPORTED_CONCERN",
    "SUSPICIOUS_NETWORK_LINK",
    "TEMPORAL_FLOW_CONFIRMED",
    "INDEPENDENT_REPORT",
    "EXPLAINED_ACTIVITY",
    "ESTABLISHED_RELATIONSHIP",
]
ContextKind = Literal["FAMILY_TRANSFER", "PAYROLL", "MERCHANT_SETTLEMENT", "REFUND", "CONFIRMED_REPORT"]
Scope = Literal["complete", "partial"]
EXPLANATIONS = frozenset({"FAMILY_TRANSFER", "PAYROLL", "MERCHANT_SETTLEMENT", "REFUND"})

ACTIONS: dict[Decision, tuple[Action, ...]] = {
    "ALLOW": ("CONTINUE_SIMULATION",),
    "WARN": ("CANCEL", "REVIEW_DETAILS", "CONTACT_OFFICIAL_SUPPORT", "CONTINUE_SIMULATION"),
    "STEP_UP": ("CANCEL", "REVIEW_DETAILS", "CONTACT_OFFICIAL_SUPPORT"),
    "LIMITED_SIGNAL": ("CANCEL", "REVIEW_DETAILS", "CONTACT_OFFICIAL_SUPPORT"),
    "UNAVAILABLE": ("RETRY", "CANCEL"),
}


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContextFact(Record):
    source_ref: str
    kind: ContextKind
    recipient: str
    occurred_at: AwareDatetime
    known_at: AwareDatetime
    transaction_ids: tuple[str, ...] = ()


class TimedTransfer(Record):
    observed: ObservedTransfer
    known_at: AwareDatetime

    def available(self, as_of: datetime) -> bool:
        transfer = self.observed
        # With date-only records, the cutoff day may contain events that have yet to occur.
        occurred = (
            transfer.occurred_at <= as_of if transfer.occurred_at is not None else transfer.observed_date < as_of.date()
        )
        return occurred and self.known_at <= as_of


class Indicator(Record):
    evidence_id: str
    family: Family
    status: SignalStatus
    reason_code: str
    transaction_ids: tuple[str, ...]


class FormationProfile(Record):
    formation_id: str
    kind: FormationKind
    band: Band
    limitations: tuple[str, ...]
    indicators: tuple[Indicator, ...]


class RecipientProfile(Record):
    schema_version: Literal[1] = 1
    snapshot_id: str
    recipient: str
    sender: str
    currency: Literal["KZT"] = "KZT"
    as_of: AwareDatetime
    valid_until: AwareDatetime
    graph_snapshot_id: str
    graph_config_sha256: str
    graph_policy_version: str
    limitations: tuple[Limitation, ...]
    is_repeat_recipient: bool
    formations: tuple[FormationProfile, ...]
    transactions: tuple[TimedTransfer, ...]
    context: tuple[ContextFact, ...]

    def identity(self) -> str:
        payload = self.model_dump(mode="json", exclude={"snapshot_id"})
        return stable_uuid("transfer-profile", sha256_hex(canonical_json(payload)))

    @model_validator(mode="after")
    def validate_provenance(self) -> RecipientProfile:
        transfers = {row.observed.transaction_id: row for row in self.transactions}
        if any(not row.available(self.as_of) or row.observed.currency != self.currency for row in self.transactions):
            raise ValueError("snapshot contains unavailable or incompatible transactions")
        if any(
            fact.recipient != self.recipient
            or max(fact.occurred_at, fact.known_at) > self.as_of
            or not transfers.keys() >= set(fact.transaction_ids)
            for fact in self.context
        ):
            raise ValueError("snapshot contains unavailable or incompatible context")
        if any(
            not transfers.keys() >= set(indicator.transaction_ids)
            for formation in self.formations
            for indicator in formation.indicators
        ):
            raise ValueError("snapshot evidence does not resolve")
        if self.snapshot_id != self.identity():
            raise ValueError("snapshot ID does not match its content")
        return self


@dataclass(frozen=True)
class TransferIntent:
    scenario_id: str
    sender: str
    recipient: str
    as_of: datetime
    amount_minor: int
    currency: str = "KZT"


class Policy(Record):
    version: StrictStr
    warn_with_confirmed_report_alone: StrictBool


@dataclass(frozen=True)
class Outcome:
    assessment_id: str
    decision: Decision
    risk_band: RiskBand
    coverage: Coverage
    reason_codes: tuple[Reason, ...]
    snapshot_id: str | None
    policy_version: str

    @property
    def recommended_actions(self) -> tuple[Action, ...]:
        return ACTIONS[self.decision]


def explained_formation(formation: FormationProfile, context: tuple[ContextFact, ...]) -> bool:
    # A settlement/refund/etc. must account for the structural and supported temporal evidence.
    flow_refs = {
        tx
        for indicator in formation.indicators
        if indicator.family in {"STRUCTURE", "TEMPORAL"} and indicator.status == "supported"
        for tx in indicator.transaction_ids
    }
    return bool(flow_refs) and any(
        fact.kind in EXPLANATIONS and flow_refs <= set(fact.transaction_ids) for fact in context
    )


def assess(
    intent: TransferIntent,
    profile: RecipientProfile | None,
    policy: Policy,
    *,
    failure: Failure | None = None,
) -> Outcome:
    if profile and (
        (profile.recipient, profile.sender, profile.currency) != (intent.recipient, intent.sender, intent.currency)
        or profile.as_of > intent.as_of
    ):
        profile, failure = None, "DEPENDENCY_FAILURE"

    def outcome(decision: Decision, band: RiskBand, coverage: Coverage, *reasons: Reason) -> Outcome:
        snapshot_id = profile.snapshot_id if profile and not failure else None
        assessment_id = stable_uuid(
            "transfer-assessment",
            intent.scenario_id,
            intent.sender,
            intent.recipient,
            intent.currency,
            str(intent.amount_minor),
            intent.as_of.isoformat(),
            snapshot_id or "",
            policy.version,
            str(policy.warn_with_confirmed_report_alone),
            decision,
            *reasons,
        )
        return Outcome(assessment_id, decision, band, coverage, reasons, snapshot_id, policy.version)

    if failure:
        return outcome("UNAVAILABLE", "UNKNOWN", "UNAVAILABLE", failure)
    if profile is None:
        return outcome("LIMITED_SIGNAL", "UNKNOWN", "LIMITED", "MISSING_PROFILE")

    limitations = profile.limitations
    if profile.valid_until < intent.as_of:
        limitations = (*limitations, "STALE_PROFILE")
    if limitations:
        return outcome("LIMITED_SIGNAL", "UNKNOWN", "LIMITED", *limitations)

    # One coherent finding is enough to warn. Overlapping formations, multiple structures
    # and peer statistics derived from the same ledger never count as independent confirmation.
    covered_by_context = False
    coherent_concern = False
    for formation in profile.formations:
        if explained_formation(formation, profile.context):
            covered_by_context = True
            continue
        supported = {
            item.family for item in formation.indicators if item.status == "supported" and item.transaction_ids
        }
        peer_counterevidence = any(
            item.family == "PEER_STATISTICS" and item.status == "contradicted" for item in formation.indicators
        )
        if {"STRUCTURE", "TEMPORAL"} <= supported and not peer_counterevidence:
            coherent_concern = True

    report = any(fact.kind == "CONFIRMED_REPORT" and not fact.transaction_ids for fact in profile.context)
    if coherent_concern:
        reasons: tuple[Reason, ...] = ("SUSPICIOUS_NETWORK_LINK", "TEMPORAL_FLOW_CONFIRMED")
        if report:
            return outcome("STEP_UP", "HIGH", "SUFFICIENT", *reasons, "INDEPENDENT_REPORT")
        return outcome("WARN", "ELEVATED", "SUFFICIENT", *reasons)
    if report and policy.warn_with_confirmed_report_alone:
        return outcome("WARN", "ELEVATED", "SUFFICIENT", "INDEPENDENT_REPORT")
    if covered_by_context:
        return outcome("ALLOW", "LOW", "SUFFICIENT", "EXPLAINED_ACTIVITY")
    if profile.is_repeat_recipient:
        return outcome("ALLOW", "LOW", "SUFFICIENT", "NO_SUPPORTED_CONCERN", "ESTABLISHED_RELATIONSHIP")
    return outcome("ALLOW", "LOW", "SUFFICIENT", "NO_SUPPORTED_CONCERN")
