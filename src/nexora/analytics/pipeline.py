"""Pure analysis orchestration: transfers -> snapshot -> formations -> evidence -> risk.

No database or web framework is imported here (spec §4.2). Every identifier is derived
from content so the same input and configuration always produce the same outputs.

Every detector emits the same bundle (``_emit``): a structural signal with recomputable
``graph_fact`` evidence, a temporal signal from the capacity-constrained flow engine, an
optional peer-statistics signal for hub-type formations, and coverage evidence. The
single risk policy then turns the bundle into a triage assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from nexora.analytics import risk as risk_engine
from nexora.analytics.config import AnalysisConfig
from nexora.analytics.context import VerifiedContext, corroboration, observable
from nexora.analytics.coverage import assess_coverage
from nexora.analytics.evidence_validation import EvidenceIntegrityError, validate_evidence
from nexora.analytics.graph_builder import GRAPH_VERSION, CurrencyGraph, GraphSnapshotData, build_snapshot
from nexora.analytics.statistical import peer as peer_mod
from nexora.analytics.structural import chain as chain_mod
from nexora.analytics.structural import cycle as cycle_mod
from nexora.analytics.structural import fan_out as fan_out_mod
from nexora.analytics.structural import funnel as funnel_mod
from nexora.analytics.temporal import flow as flow_mod
from nexora.domain.analysis import (
    CoverageAssessment,
    Evidence,
    EvidenceKind,
    Formation,
    FormationKind,
    ReasonCode,
    RiskAssessment,
    Signal,
)
from nexora.domain.ids import canonical_json, sha256_hex, stable_uuid
from nexora.domain.money import amount_to_str
from nexora.domain.transfers import ObservedTransfer


@dataclass
class AnalysisOutput:
    snapshot_id: str
    snapshot: GraphSnapshotData
    graph_version: str
    config_sha256: str
    policy_sha256: str
    policy_version: str
    formations: list[Formation] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    assessments: list[RiskAssessment] = field(default_factory=list)
    quarantined: list[dict[str, str]] = field(default_factory=list)
    partial_reasons: list[str] = field(default_factory=list)


def snapshot_identity(dataset_id: str, input_manifest_sha256: str, config_sha256: str) -> str:
    return stable_uuid("snapshot", dataset_id, input_manifest_sha256, config_sha256, GRAPH_VERSION)


def _enabled(cfg: dict[str, Any] | None) -> bool:
    return cfg is not None and bool(cfg.get("enabled", True))


def _flow_reason(result: flow_mod.FlowResult, supported_code: str) -> ReasonCode:
    if result.status == "supported":
        return ReasonCode(
            supported_code,
            {
                "compatible_minor": amount_to_str(result.strict_compatible_minor)
                if result.strict_compatible_minor
                else "0",
                "entry_minor": amount_to_str(result.entry_minor) if result.entry_minor else "0",
                "fraction_bp": result.compatible_fraction_bp,
                "lag_days_min": result.lag_days_min,
                "lag_days_max": result.lag_days_max,
                "precision": result.precision,
            },
        )
    if result.status == "possible_ambiguous":
        return ReasonCode(
            "TEMPORAL_SAME_DAY_AMBIGUOUS",
            {
                "uncertain_count": result.uncertain_transition_count,
                "fraction_bp": result.compatible_fraction_bp,
            },
        )
    if result.status == "contradicted":
        return ReasonCode("TEMPORAL_CONTRADICTED", {"fraction_bp": result.compatible_fraction_bp})
    return ReasonCode("TEMPORAL_UNAVAILABLE", {"reason": result.limitations[0] if result.limitations else "unknown"})


def _peer_reason(res: peer_mod.PeerResult) -> ReasonCode:
    params: dict[str, Any] = {
        "burst_bp": res.subject.burst_bp,
        "window_days": res.window_days,
        "cohort_size": res.cohort_size,
    }
    if res.status == "supported":
        return ReasonCode("PEER_CONCENTRATION_OUTLIER", {**params, "fence_bp": res.fence_bp})
    if res.status == "contradicted":
        return ReasonCode("PEER_TYPICAL_TURNOVER", {**params, "median_bp": res.cohort_median_bp})
    if res.status == "possible_ambiguous":
        return ReasonCode("PEER_INCONCLUSIVE", {**params, "fence_bp": res.fence_bp})
    return ReasonCode("PEER_UNAVAILABLE", {"cohort_size": res.cohort_size})


def _money(v: int) -> str:
    return str(v)


@dataclass
class _Structure:
    """Detector-specific part of a formation bundle."""

    kind: FormationKind
    detector_id: str
    detector_version: str
    fid: str
    subject: str
    member_ids: tuple[str, ...]
    entry_ids: tuple[str, ...]
    exit_ids: tuple[str, ...]
    evidence: Evidence
    strength: float
    dependency_tags: tuple[str, ...]
    reason: ReasonCode
    features: dict[str, Any]
    layers: list[list[str]]  # temporal flow layers (transaction ids)
    temporal_code: str
    has_downstream: bool
    coverage_members: tuple[str, ...]
    peer: bool  # evaluate account-level peer statistics for the subject (hub-type formations)


class _Builder:
    def __init__(
        self,
        dataset_id: str,
        snapshot: GraphSnapshotData,
        config: AnalysisConfig,
        contract: dict[str, Any],
        context: VerifiedContext | None,
    ):
        self.snapshot = snapshot
        self.config = config
        self.contract = contract
        self.context = context
        self.snapshot_id = snapshot_identity(dataset_id, snapshot.input_manifest_sha256, config.config_sha256)
        self.out = AnalysisOutput(
            snapshot_id=self.snapshot_id,
            snapshot=snapshot,
            graph_version=GRAPH_VERSION,
            config_sha256=config.config_sha256,
            policy_sha256=config.policy_sha256,
            policy_version=config.policy_version,
        )
        self._peer_index: dict[str, peer_mod.PeerIndex] = {}

    # -- helpers -----------------------------------------------------------------
    def _detector_config(self, name: str, currency: str) -> dict[str, Any]:
        config = self.config.detectors[name]
        defaults = self.config.detectors.get("currency_thresholds", {})
        overrides = defaults.get(currency, {}).get(name, {})
        return {**config, **overrides} if overrides else config

    def _transfers(self, ids: tuple[str, ...] | list[str]) -> list[ObservedTransfer]:
        return [self.snapshot.transfers[i] for i in ids]

    def _temporal_evidence(
        self,
        formation_id: str,
        result: flow_mod.FlowResult,
        account_ids: tuple[str, ...],
        supported_code: str,
    ) -> Evidence:
        tcfg = self.config.detectors["temporal"]
        kind: EvidenceKind = "counterevidence" if result.status == "contradicted" else "temporal_fact"
        code = _flow_reason(result, supported_code).code
        coverage = {}
        if self.config.risk_policy.get("verified_context"):
            eligible, processed = result.eligible_transfers, result.processed_transfers
            coverage = {
                "eligible_transfers": eligible,
                "processed_transfers": processed,
                "skipped_transfers": eligible - processed,
                "coverage_bp": processed * 10_000 // eligible if eligible else None,
            }
        return Evidence(
            id=stable_uuid("evidence", formation_id, "temporal"),
            kind=kind,
            reason_code=code,
            subject_id=formation_id,
            transaction_ids=result.supporting_transaction_ids,
            account_ids=account_ids,
            observations={
                "status": result.status,
                "method": result.method,
                "entry_minor": _money(result.entry_minor),
                "strict_compatible_minor": _money(result.strict_compatible_minor),
                "possible_compatible_minor": _money(result.possible_compatible_minor),
                "compatible_fraction_bp": result.compatible_fraction_bp,
                "uncertain_transition_count": result.uncertain_transition_count,
                "lag_days_min": result.lag_days_min,
                "lag_days_max": result.lag_days_max,
                "lag_seconds_min": result.lag_seconds_min,
                "lag_seconds_max": result.lag_seconds_max,
                "time_precision": result.precision,
                **coverage,
            },
            thresholds={
                "max_hop_lag_days": int(tcfg["max_hop_lag_days"]),
                "min_compatible_fraction": str(tcfg["min_compatible_fraction"]),
            },
            limitations=result.limitations,
            detector_version=str(tcfg["detector_version"]),
        )

    def _temporal_signal(self, formation_id: str, result: flow_mod.FlowResult, evidence_id: str) -> Signal:
        tcfg = self.config.detectors["temporal"]
        strength: float | None
        if result.status == "supported":
            strength = min(1.0, result.compatible_fraction_bp / 10_000)
        elif result.status == "possible_ambiguous":
            strength = float(self.config.risk_policy["temporal_strength"]["possible_ambiguous"])
        elif result.status == "contradicted":
            strength = float(self.config.risk_policy["temporal_strength"]["contradicted"])
        else:
            strength = None
        return Signal(
            id=stable_uuid("signal", formation_id, flow_mod.DETECTOR_ID),
            formation_id=formation_id,
            family="TEMPORAL",
            detector_id=flow_mod.DETECTOR_ID,
            detector_version=str(tcfg["detector_version"]),
            status=result.status,
            strength=strength,
            evidence_ids=(evidence_id,),
            limitations=result.limitations,
            dependency_tags=("temporal.flow",),
        )

    def _peer(self, cg: CurrencyGraph, formation_id: str, subject: str) -> tuple[Evidence, Signal, ReasonCode] | None:
        pcfg = self.config.detectors.get("peer")
        if not _enabled(pcfg):
            return None
        assert pcfg is not None
        index = self._peer_index.get(cg.currency)
        if index is None:
            index = peer_mod.PeerIndex(cg, self.snapshot.transfers, int(pcfg["window_days"]))
            self._peer_index[cg.currency] = index
        res = index.assess(subject, pcfg)
        reason = _peer_reason(res)
        prof = res.subject
        observations: dict[str, Any] = {
            "status": res.status,
            "account_id": subject,
            "currency": cg.currency,
            "transfer_count": prof.transfer_count,
            "turnover_minor": _money(prof.turnover_minor),
            "cohort_size": res.cohort_size,
            "cohort_count_factor": res.cohort_factor,
            "cohort_q1_bp": res.cohort_q1_bp,
            "cohort_median_bp": res.cohort_median_bp,
            "cohort_q3_bp": res.cohort_q3_bp,
            "fence_bp": res.fence_bp,
        }
        tx_ids: tuple[str, ...] = ()
        if prof.turnover_minor > 0:
            tx_ids = prof.burst_transaction_ids
            observations |= {
                "window_minor": _money(prof.burst_minor),
                "burst_share_bp": prof.burst_bp,
                "window_start": prof.burst_start.isoformat() if prof.burst_start else None,
            }
        ev = Evidence(
            id=stable_uuid("evidence", formation_id, "peer"),
            kind="counterevidence" if res.status == "contradicted" else "statistical_fact",
            reason_code=reason.code,
            subject_id=formation_id,
            transaction_ids=tx_ids,
            account_ids=(subject,),
            observations=observations,
            thresholds={
                "window_days": int(pcfg["window_days"]),
                "min_cohort": int(pcfg["min_cohort"]),
                "cohort_count_factors": [int(f) for f in pcfg["cohort_count_factors"]],
                "fence_iqr_multiplier": str(pcfg["fence_iqr_multiplier"]),
                "min_burst_share": str(pcfg["min_burst_share"]),
            },
            limitations=res.limitations,
            detector_version=str(pcfg["detector_version"]),
        )
        sig = Signal(
            id=stable_uuid("signal", formation_id, peer_mod.DETECTOR_ID),
            formation_id=formation_id,
            family="PEER_STATISTICS",
            detector_id=peer_mod.DETECTOR_ID,
            detector_version=str(pcfg["detector_version"]),
            status=res.status,
            strength=res.strength,
            evidence_ids=(ev.id,),
            limitations=res.limitations,
            dependency_tags=("account.time_concentration",),
        )
        return ev, sig, reason

    def _coverage_evidence(self, formation_id: str, coverage: CoverageAssessment, detector_version: str) -> Evidence:
        return Evidence(
            id=stable_uuid("evidence", formation_id, "coverage"),
            kind="coverage_fact",
            reason_code="COVERAGE_LIMITATIONS",
            subject_id=formation_id,
            transaction_ids=(),
            account_ids=coverage.boundary_accounts,
            observations={
                "limitations": list(coverage.limitations),
                "subject_limitations": list(coverage.subject_limitations),
                "boundary_accounts": list(coverage.boundary_accounts),
                "data_requests": [r.as_dict() for r in coverage.data_requests],
            },
            thresholds={},
            limitations=coverage.limitations,
            detector_version=detector_version,
        )

    @staticmethod
    def _coverage_reasons(coverage: CoverageAssessment, subject: str) -> list[ReasonCode]:
        out: list[ReasonCode] = []
        if "boundary_limited" in coverage.limitations:
            out.append(ReasonCode("COVERAGE_BOUNDARY", {"accounts": list(coverage.boundary_accounts)}))
        if "downstream_unobserved" in coverage.limitations:
            out.append(ReasonCode("COVERAGE_DOWNSTREAM_UNOBSERVED", {"account_id": subject}))
        if "upstream_unknown" in coverage.limitations:
            out.append(ReasonCode("COVERAGE_UPSTREAM_UNKNOWN"))
        if "timestamp_precision_limited" in coverage.limitations:
            out.append(ReasonCode("COVERAGE_DAY_PRECISION"))
        return out

    def _emit(self, cg: CurrencyGraph, st: _Structure) -> None:
        tcfg = self.config.detectors["temporal"]
        flow = flow_mod.layered_flow(
            [self._transfers(layer) for layer in st.layers],
            max_lag_days=int(tcfg["max_hop_lag_days"]),
            min_compatible_fraction=str(tcfg["min_compatible_fraction"]),
            max_transfers=int(tcfg["max_transfers"]),
        )
        temporal_accounts = tuple(dict.fromkeys((*st.entry_ids, *st.member_ids, *st.exit_ids)))
        temporal_ev = self._temporal_evidence(st.fid, flow, temporal_accounts, st.temporal_code)
        all_tx = sorted(set(st.evidence.transaction_ids) | set(temporal_ev.transaction_ids))
        dates: list[date] = [self.snapshot.transfers[t].observed_date for t in all_tx]
        coverage = assess_coverage(
            kind=st.kind,
            subject_account_id=st.subject,
            member_ids=st.coverage_members,
            entry_ids=st.entry_ids,
            exit_ids=st.exit_ids,
            has_downstream=st.has_downstream,
            transfers=self._transfers(all_tx),
            flow=flow,
            contract=self.contract,
            window=(min(dates), max(dates)),
        )
        cov_ev = self._coverage_evidence(st.fid, coverage, st.detector_version)
        struct_sig = Signal(
            id=stable_uuid("signal", st.fid, st.detector_id),
            formation_id=st.fid,
            family="STRUCTURE",
            detector_id=st.detector_id,
            detector_version=st.detector_version,
            status="supported",
            strength=st.strength,
            evidence_ids=(st.evidence.id,),
            limitations=st.evidence.limitations,
            dependency_tags=st.dependency_tags,
        )
        evidence = [st.evidence, temporal_ev, cov_ev]
        signals = [struct_sig, self._temporal_signal(st.fid, flow, temporal_ev.id)]
        reasons = [st.reason, _flow_reason(flow, st.temporal_code)]
        peer = self._peer(cg, st.fid, st.subject) if st.peer else None
        features = {**st.features, "temporal_status": flow.status}
        if peer is not None:
            peer_ev, peer_sig, peer_reason = peer
            evidence.append(peer_ev)
            signals.append(peer_sig)
            reasons.append(peer_reason)
            features["peer_status"] = peer_sig.status
        if self.context is not None:
            context_bundle = corroboration(self.context, st.fid, st.subject, cg.currency, self._transfers(all_tx))
            if context_bundle is not None:
                context_ev, context_signal, context_reason = context_bundle
                evidence.append(context_ev)
                signals.append(context_signal)
                reasons.append(context_reason)
        reasons.extend(self._coverage_reasons(coverage, st.subject))
        formation = Formation(
            id=st.fid,
            kind=st.kind,
            currency=cg.currency,
            subject_account_id=st.subject,
            member_ids=st.member_ids,
            entry_ids=st.entry_ids,
            exit_ids=st.exit_ids,
            features=features,
            limitations=coverage.limitations,
            detector_id=st.detector_id,
            detector_version=st.detector_version,
            window_start=min(dates),
            window_end=max(dates),
            transaction_ids=tuple(all_tx),
        )
        try:
            for ev in evidence:
                validate_evidence(ev, self.snapshot.transfers)
        except EvidenceIntegrityError as exc:
            self.out.quarantined.append({"formation_id": formation.id, "error": str(exc)})
            return
        assessment = risk_engine.assess(
            formation_id=formation.id,
            signals=signals,
            coverage=coverage,
            reasons=reasons,
            policy=self.config.risk_policy,
            policy_sha256=self.config.policy_sha256,
        )
        self.out.formations.append(formation)
        self.out.evidence.extend(evidence)
        self.out.signals.extend(signals)
        self.out.assessments.append(assessment)

    # -- detectors ---------------------------------------------------------------
    def funnels(self, cg: CurrencyGraph) -> None:
        fcfg = self._detector_config("funnel", cg.currency)
        for cand in funnel_mod.detect_funnels(cg, fcfg):
            feeders = tuple(f.account_id for f in cand.feeders)
            members = (*feeders, cand.center)
            fid = stable_uuid("formation", self.snapshot_id, "funnel", cg.currency, cand.center, *sorted(feeders))
            entry_tx = [t for f in cand.feeders for t in f.transaction_ids]
            out_tx = [
                tid
                for (snd, rcv), e in sorted(cg.edges.items())
                if snd == cand.center and rcv != cand.center
                for tid in e.transaction_ids
            ]
            observations: dict[str, Any] = {
                "center": cand.center,
                "feeder_count": len(cand.feeders),
                "total_minor": _money(cand.total_incoming_minor),
                "currency": cg.currency,
                "feeders": [
                    {
                        "account_id": f.account_id,
                        "edge_minor": _money(f.edge_minor),
                        "sender_outgoing_minor": _money(f.sender_outgoing_minor),
                        "share_bp": f.share_bp,
                        "transaction_count": len(f.transaction_ids),
                    }
                    for f in cand.feeders
                ],
                "downstream_accounts": list(cand.downstream),
            }
            if fcfg.get("exclude_returning_feeders"):
                observations["returning_feeders"] = list(cand.returning_feeders)
            struct_ev = Evidence(
                id=stable_uuid("evidence", fid, "structure"),
                kind="graph_fact",
                reason_code="STRUCT_FUNNEL_FEEDERS",
                subject_id=fid,
                transaction_ids=tuple(sorted(entry_tx)),
                account_ids=members,
                observations=observations,
                thresholds={
                    "min_feeders": int(fcfg["min_feeders"]),
                    "min_feeder_share": str(fcfg["min_feeder_share"]),
                    "min_incoming_minor": str(fcfg["min_incoming_minor"]),
                },
                limitations=("structural_only",),
                detector_version=str(fcfg["detector_version"]),
            )
            self._emit(
                cg,
                _Structure(
                    kind="funnel",
                    detector_id=funnel_mod.DETECTOR_ID,
                    detector_version=str(fcfg["detector_version"]),
                    fid=fid,
                    subject=cand.center,
                    member_ids=members,
                    entry_ids=feeders,
                    exit_ids=cand.downstream,
                    evidence=struct_ev,
                    strength=funnel_mod.funnel_strength(len(cand.feeders), int(fcfg["min_feeders"])),
                    dependency_tags=("graph.in_degree", "graph.edge_share"),
                    reason=ReasonCode(
                        "STRUCT_FUNNEL_FEEDERS",
                        {
                            "count": len(cand.feeders),
                            "total_minor": _money(cand.total_incoming_minor),
                            "currency": cg.currency,
                        },
                    ),
                    features={
                        "feeder_count": len(cand.feeders),
                        "incoming_minor": _money(cand.total_incoming_minor),
                        "downstream_count": len(cand.downstream),
                    },
                    layers=[entry_tx, out_tx],
                    temporal_code="TEMPORAL_PASS_THROUGH_SUPPORTED",
                    has_downstream=bool(cand.downstream),
                    coverage_members=(*members, *cand.downstream),
                    peer=True,
                ),
            )

    def fan_outs(self, cg: CurrencyGraph) -> None:
        ocfg = self.config.detectors.get("fan_out")
        if not _enabled(ocfg):
            return
        assert ocfg is not None
        ocfg = self._detector_config("fan_out", cg.currency)
        for cand in fan_out_mod.detect_fan_outs(cg, ocfg):
            dist = cand.distributor
            recipients = tuple(r.account_id for r in cand.recipients)
            fid = stable_uuid("formation", self.snapshot_id, "fan_out", cg.currency, dist, *sorted(recipients))
            in_tx = [
                tid
                for (snd, rcv), e in sorted(cg.edges.items())
                if rcv == dist and snd != dist
                for tid in e.transaction_ids
            ]
            out_tx = sorted(t for r in cand.recipients for t in r.transaction_ids)
            struct_ev = Evidence(
                id=stable_uuid("evidence", fid, "structure"),
                kind="graph_fact",
                reason_code="STRUCT_FAN_OUT_RECIPIENTS",
                subject_id=fid,
                transaction_ids=tuple(out_tx),
                account_ids=(dist, *recipients),
                observations={
                    "distributor": dist,
                    "recipient_count": len(recipients),
                    "onward_count": cand.onward_count,
                    "total_minor": _money(cand.total_outgoing_minor),
                    "currency": cg.currency,
                    "recipients": [
                        {
                            "account_id": r.account_id,
                            "edge_minor": _money(r.edge_minor),
                            "receiver_incoming_minor": _money(r.receiver_incoming_minor),
                            "share_bp": r.share_bp,
                            "transaction_count": len(r.transaction_ids),
                            "forwards_onward": r.forwards_onward,
                        }
                        for r in cand.recipients
                    ],
                    "source_accounts": list(cand.sources),
                    "returning_recipients": list(cand.returning_recipients),
                },
                thresholds={
                    "min_recipients": int(ocfg["min_recipients"]),
                    "min_recipient_share": str(ocfg["min_recipient_share"]),
                    "min_outgoing_minor": str(ocfg["min_outgoing_minor"]),
                },
                limitations=("structural_only",),
                detector_version=str(ocfg["detector_version"]),
            )
            self._emit(
                cg,
                _Structure(
                    kind="fan_out",
                    detector_id=fan_out_mod.DETECTOR_ID,
                    detector_version=str(ocfg["detector_version"]),
                    fid=fid,
                    subject=dist,
                    member_ids=(dist, *recipients),
                    entry_ids=cand.sources,
                    exit_ids=recipients,
                    evidence=struct_ev,
                    strength=fan_out_mod.fan_out_strength(len(recipients), int(ocfg["min_recipients"])),
                    dependency_tags=("graph.out_degree", "graph.edge_share"),
                    reason=ReasonCode(
                        "STRUCT_FAN_OUT_RECIPIENTS",
                        {
                            "count": len(recipients),
                            "total_minor": _money(cand.total_outgoing_minor),
                            "currency": cg.currency,
                            "onward_count": cand.onward_count,
                        },
                    ),
                    features={
                        "recipient_count": len(recipients),
                        "outgoing_minor": _money(cand.total_outgoing_minor),
                        "source_count": len(cand.sources),
                        "onward_count": cand.onward_count,
                    },
                    layers=[in_tx, out_tx],
                    temporal_code="TEMPORAL_DISTRIBUTION_SUPPORTED",
                    has_downstream=cand.onward_count > 0,
                    coverage_members=(*cand.sources, dist, *recipients),
                    peer=True,
                ),
            )

    def cycles(self, cg: CurrencyGraph) -> list[frozenset[str]]:
        ycfg = self.config.detectors.get("cycle")
        if not _enabled(ycfg):
            return []
        assert ycfg is not None
        ycfg = self._detector_config("cycle", cg.currency)
        detection = cycle_mod.detect_cycles(cg, ycfg)
        if detection.budget_exceeded:
            self.out.partial_reasons.append(f"cycle_budget_exceeded:{cg.currency}")
        loops: list[frozenset[str]] = []
        for cand in detection.candidates:
            members = cand.members
            loops.append(frozenset(members))
            fid = stable_uuid("formation", self.snapshot_id, "cycle", cg.currency, *members)
            hop_tx = [list(cg.edges[e].transaction_ids) for e in cand.edges()]
            struct_tx = sorted(t for h in hop_tx for t in h)
            struct_ev = Evidence(
                id=stable_uuid("evidence", fid, "structure"),
                kind="graph_fact",
                reason_code="STRUCT_CYCLE_LOOP",
                subject_id=fid,
                transaction_ids=tuple(struct_tx),
                account_ids=members,
                observations={
                    "loop": list(members),
                    "length": cand.length,
                    "currency": cg.currency,
                    "total_minor": _money(sum(self.snapshot.transfers[t].amount_minor for t in struct_tx)),
                    "hop_edges": [
                        {
                            "sender": u,
                            "receiver": v,
                            "edge_minor": _money(cg.edges[(u, v)].amount_minor),
                            "transaction_count": len(hop_tx[i]),
                        }
                        for i, (u, v) in enumerate(cand.edges())
                    ],
                },
                thresholds={
                    "min_length": int(ycfg["min_length"]),
                    "max_length": int(ycfg["max_length"]),
                    "member_max_degree": int(ycfg["member_max_degree"]),
                    "min_edge_minor": str(ycfg["min_edge_minor"]),
                    "hop_amount_min_ratio": str(ycfg["hop_amount_min_ratio"]),
                },
                limitations=("structural_only", "loop_does_not_prove_same_funds"),
                detector_version=str(ycfg["detector_version"]),
            )
            self._emit(
                cg,
                _Structure(
                    kind="cycle",
                    detector_id=cycle_mod.DETECTOR_ID,
                    detector_version=str(ycfg["detector_version"]),
                    fid=fid,
                    subject=members[0],
                    member_ids=members,
                    entry_ids=(members[0],),
                    exit_ids=(members[0],),
                    evidence=struct_ev,
                    strength=cycle_mod.cycle_strength(cand.length, int(ycfg["min_length"])),
                    dependency_tags=("graph.cycle",),
                    reason=ReasonCode("STRUCT_CYCLE_LOOP", {"length": cand.length, "currency": cg.currency}),
                    features={"length": cand.length, "total_minor": struct_ev.observations["total_minor"]},
                    layers=hop_tx,
                    temporal_code="TEMPORAL_LOOP_SUPPORTED",
                    has_downstream=True,
                    coverage_members=members,
                    peer=False,
                ),
            )
        return loops

    def chains(self, cg: CurrencyGraph, loops: list[frozenset[str]]) -> None:
        ccfg = self._detector_config("chain", cg.currency)
        detection = chain_mod.detect_chains(cg, ccfg)
        if detection.budget_exceeded:
            self.out.partial_reasons.append(f"path_budget_exceeded:{cg.currency}")
        for cand in detection.candidates:
            path = cand.path
            if any(set(path) <= loop for loop in loops):
                continue  # deduplicated: the same accounts are already reported as a closed loop
            fid = stable_uuid("formation", self.snapshot_id, "chain", cg.currency, *path)
            hop_tx = [list(cg.edges[(path[i], path[i + 1])].transaction_ids) for i in range(cand.hops)]
            struct_tx = sorted(t for h in hop_tx for t in h)
            struct_ev = Evidence(
                id=stable_uuid("evidence", fid, "structure"),
                kind="graph_fact",
                reason_code="STRUCT_CHAIN_PATH",
                subject_id=fid,
                transaction_ids=tuple(struct_tx),
                account_ids=path,
                observations={
                    "path": list(path),
                    "hops": cand.hops,
                    "currency": cg.currency,
                    "total_minor": _money(sum(self.snapshot.transfers[t].amount_minor for t in struct_tx)),
                    "hop_edges": [
                        {
                            "sender": path[i],
                            "receiver": path[i + 1],
                            "edge_minor": _money(cg.edges[(path[i], path[i + 1])].amount_minor),
                            "transaction_count": len(hop_tx[i]),
                        }
                        for i in range(cand.hops)
                    ],
                },
                thresholds={
                    "min_hops": int(ccfg["min_hops"]),
                    "intermediary_max_degree": int(ccfg["intermediary_max_degree"]),
                    "pass_through_min_ratio": str(ccfg["pass_through_min_ratio"]),
                    "min_edge_minor": str(ccfg["min_edge_minor"]),
                },
                limitations=("structural_only", "path_does_not_prove_same_funds"),
                detector_version=str(ccfg["detector_version"]),
            )
            self._emit(
                cg,
                _Structure(
                    kind="chain",
                    detector_id=chain_mod.DETECTOR_ID,
                    detector_version=str(ccfg["detector_version"]),
                    fid=fid,
                    subject=path[-1],
                    member_ids=path,
                    entry_ids=(path[0],),
                    exit_ids=(path[-1],),
                    evidence=struct_ev,
                    strength=chain_mod.chain_strength(cand.hops, int(ccfg["min_hops"])),
                    dependency_tags=("graph.path",),
                    reason=ReasonCode("STRUCT_CHAIN_PATH", {"hops": cand.hops, "currency": cg.currency}),
                    features={"hops": cand.hops},
                    layers=hop_tx,
                    temporal_code="TEMPORAL_PATH_SUPPORTED",
                    has_downstream=True,
                    coverage_members=path,
                    peer=False,
                ),
            )


def run_analysis(
    *,
    dataset_id: str,
    transfers: list[ObservedTransfer],
    contract: dict[str, Any],
    config: AnalysisConfig,
    context: VerifiedContext | None = None,
) -> AnalysisOutput:
    active_context = context if config.risk_policy.get("verified_context") else None
    snapshot = build_snapshot(
        [row for row in transfers if observable(row, active_context.as_of)] if active_context is not None else transfers
    )
    if active_context is not None:
        snapshot.input_manifest_sha256 = sha256_hex(
            canonical_json([snapshot.input_manifest_sha256, active_context.manifest()])
        )
    builder = _Builder(dataset_id, snapshot, config, contract, active_context)
    for currency in snapshot.currencies:
        cg = snapshot.by_currency[currency]
        builder.funnels(cg)
        builder.fan_outs(cg)
        loops = builder.cycles(cg)
        builder.chains(cg, loops)
    out = builder.out
    out.formations.sort(key=lambda f: f.id)
    out.evidence.sort(key=lambda e: e.id)
    out.signals.sort(key=lambda s: s.id)
    out.assessments.sort(key=lambda a: a.id)
    return out
