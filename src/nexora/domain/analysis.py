"""Typed analysis outputs shared by every detector family (ADR-004).

All JSON-bound payloads (observations, thresholds, features, params) must contain only
JSON-safe values; money is always a decimal string; ratios are integer basis points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from nexora.domain.ids import canonical_json, sha256_hex

EvidenceKind = Literal[
    "transaction_fact",
    "aggregate_fact",
    "graph_fact",
    "temporal_fact",
    "statistical_fact",
    "coverage_fact",
    "counterevidence",
]
SignalStatus = Literal["supported", "possible_ambiguous", "contradicted", "unavailable"]
Family = Literal["STRUCTURE", "TEMPORAL", "PEER_STATISTICS", "NETWORK_CONTEXT"]
Band = Literal["critical", "high", "medium", "low", "insufficient_evidence"]
BAND_ORDER: tuple[str, ...] = ("low", "medium", "high", "critical")


@dataclass(frozen=True)
class ReasonCode:
    code: str
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "params": self.params}


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: EvidenceKind
    reason_code: str
    subject_id: str
    transaction_ids: tuple[str, ...]
    account_ids: tuple[str, ...]
    observations: dict[str, Any]
    thresholds: dict[str, Any]
    limitations: tuple[str, ...]
    detector_version: str

    @property
    def provenance_hash(self) -> str:
        return sha256_hex(
            canonical_json(
                {
                    "kind": self.kind,
                    "reason_code": self.reason_code,
                    "subject_id": self.subject_id,
                    "transaction_ids": sorted(self.transaction_ids),
                    "observations": self.observations,
                    "thresholds": self.thresholds,
                    "detector_version": self.detector_version,
                }
            )
        )


@dataclass(frozen=True)
class Formation:
    id: str
    kind: Literal["funnel", "chain", "fanout", "cycle"]
    currency: str
    subject_account_id: str
    member_ids: tuple[str, ...]
    entry_ids: tuple[str, ...]
    exit_ids: tuple[str, ...]
    features: dict[str, Any]
    limitations: tuple[str, ...]
    detector_id: str
    detector_version: str
    window_start: date
    window_end: date
    transaction_ids: tuple[str, ...]


@dataclass(frozen=True)
class Signal:
    id: str
    formation_id: str
    family: Family
    detector_id: str
    detector_version: str
    status: SignalStatus
    strength: float | None
    evidence_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    dependency_tags: tuple[str, ...]


@dataclass(frozen=True)
class DataRequest:
    type: str
    subject_ids: tuple[str, ...]
    proposed_window: tuple[str, str] | None
    missing_dependency: str
    expected_resolution: str
    priority_heuristic: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "subject_ids": list(self.subject_ids),
            "proposed_window": list(self.proposed_window) if self.proposed_window else None,
            "missing_dependency": self.missing_dependency,
            "expected_resolution": self.expected_resolution,
            "priority_heuristic": self.priority_heuristic,
        }


@dataclass(frozen=True)
class CoverageAssessment:
    limitations: tuple[str, ...]
    subject_limitations: tuple[str, ...]
    boundary_accounts: tuple[str, ...]
    data_requests: tuple[DataRequest, ...]


@dataclass(frozen=True)
class RiskAssessment:
    id: str
    formation_id: str
    policy_version: str
    policy_sha256: str
    priority: int | None
    band: Band
    signal_ids: tuple[str, ...]
    supported_families: tuple[str, ...]
    missing_families: tuple[str, ...]
    coverage: CoverageAssessment
    reason_codes: tuple[ReasonCode, ...]

    def fingerprint_payload(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "priority": self.priority,
            "reasons": [r.as_dict() for r in self.reason_codes],
        }
