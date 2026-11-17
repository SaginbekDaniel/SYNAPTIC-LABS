"""Pure analysis orchestration: transfers -> snapshot -> formations -> evidence -> risk.

No database or web framework is imported here (spec §4.2). Every identifier is derived
from content so the same input and configuration always produce the same outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from nexora.analytics import attribution
from nexora.analytics import risk as risk_engine
from nexora.analytics.config import AnalysisConfig
from nexora.analytics.context import ContextIndicator, hub_context
from nexora.analytics.coverage import assess_coverage
from nexora.analytics.evidence_validation import EvidenceIntegrityError, validate_evidence
from nexora.analytics.graph_builder import GRAPH_VERSION, CurrencyGraph, GraphSnapshotData, build_snapshot
from nexora.analytics.structural import chain as chain_mod
from nexora.analytics.structural import cycle as cycle_mod
from nexora.analytics.structural import fanout as fanout_mod
from nexora.analytics.structural import funnel as funnel_mod
from nexora.analytics.temporal import episodes as episodes_mod
from nexora.analytics.temporal import flow as flow_mod
from nexora.domain.analysis import (
    CoverageAssessment,
    Evidence,
    EvidenceKind,
    Formation,
    ReasonCode,
    RiskAssessment,
    Signal,
)
from nexora.domain.ids import stable_uuid
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


def _money(v: int) -> str:
    return str(v)


class _Builder:
    def __init__(self, dataset_id: str, snapshot: GraphSnapshotData, config: AnalysisConfig, contract: dict[str, Any]):
        self.snapshot = snapshot
        self.config = config
        self.contract = contract
        self.snapshot_id = snapshot_identity(dataset_id, snapshot.input_manifest_sha256, config.config_sha256)
        self.out = AnalysisOutput(
            snapshot_id=self.snapshot_id,
            snapshot=snapshot,
            graph_version=GRAPH_VERSION,
            config_sha256=config.config_sha256,
            policy_sha256=config.policy_sha256,
            policy_version=config.policy_version,
        )

    # -- helpers -----------------------------------------------------------------
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
                **({} if result.pro_rata_minor is None else {"pro_rata_minor": _money(result.pro_rata_minor)}),
            },
            thresholds={
                "max_hop_lag_days": int(tcfg["max_hop_lag_days"]),
                "min_compatible_fraction": str(tcfg["min_compatible_fraction"]),
            },
            limitations=result.limitations,
            detector_version=str(tcfg["detector_version"]),
        )

    def _temporal_signal(
        self,
        formation_id: str,
        result: flow_mod.FlowResult,
        evidence_id: str,
        detector_id: str = flow_mod.DETECTOR_ID,
    ) -> Signal:
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
            id=stable_uuid("signal", formation_id, detector_id),
            formation_id=formation_id,
            family="TEMPORAL",
            detector_id=detector_id,
            detector_version=str(tcfg["detector_version"]),
            status=result.status,
            strength=strength,
            evidence_ids=(evidence_id,),
            limitations=result.limitations,
            dependency_tags=(detector_id,),
        )

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

    def _publish(
        self,
        formation: Formation,
        evidence: list[Evidence],
        signals: list[Signal],
        coverage: CoverageAssessment,
        reasons: list[ReasonCode],
        counterevidence: tuple[str, ...] = (),
    ) -> None:
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
            counterevidence=counterevidence,
        )
        self.out.formations.append(formation)
        self.out.evidence.extend(evidence)
        self.out.signals.extend(signals)
        self.out.assessments.append(assessment)

    def _transfers(self, ids: tuple[str, ...] | list[str]) -> list[ObservedTransfer]:
        return [self.snapshot.transfers[i] for i in ids]

    # -- v2 refinements (each enabled only by its configuration key) ----------------
    def _attributed(self, flow: flow_mod.FlowResult, pro_rata: int) -> flow_mod.FlowResult:
        """Apply fungibility-aware attribution when ``temporal.attribution: pro_rata``."""
        tcfg = self.config.detectors["temporal"]
        if tcfg.get("attribution") != "pro_rata":
            return flow
        return flow_mod.apply_attribution(flow, pro_rata, min_compatible_fraction=str(tcfg["min_compatible_fraction"]))

    def _structure_strength(self, cfg: dict[str, Any], count: int, min_count: int, shares_bp: list[int]) -> float:
        if cfg.get("strength_model") == "dedication":
            return funnel_mod.dedication_strength(shares_bp, str(cfg["min_feeder_share"]))
        return funnel_mod.funnel_strength(count, min_count)

    def _context(
        self, cg: CurrencyGraph, subject: str, counterparties: tuple[str, ...], direction: str
    ) -> list[ContextIndicator]:
        ccfg = self.config.detectors.get("context")
        if not ccfg:
            return []
        return hub_context(
            cg, self.snapshot.transfers, subject=subject, counterparties=counterparties, direction=direction, cfg=ccfg
        )

    def _context_evidence(self, formation_id: str, indicators: list[ContextIndicator]) -> list[Evidence]:
        version = str(self.config.detectors.get("context", {}).get("detector_version", "context"))
        return [
            Evidence(
                id=stable_uuid("evidence", formation_id, "context", ind.code),
                kind="counterevidence",
                reason_code=ind.code,
                subject_id=formation_id,
                transaction_ids=ind.transaction_ids,
                account_ids=(),
                observations=ind.observations,
                thresholds=ind.thresholds,
                limitations=("benign_explanation_not_verified",),
                detector_version=version,
            )
            for ind in indicators
        ]

    def _emit(
        self,
        *,
        cg: CurrencyGraph,
        kind: str,
        fid: str,
        detector_id: str,
        detector_version: str,
        subject: str,
        members: tuple[str, ...],
        entry_ids: tuple[str, ...],
        exit_ids: tuple[str, ...],
        struct_ev: Evidence,
        struct_strength: float,
        struct_tags: tuple[str, ...],
        struct_reason: ReasonCode,
        flow: flow_mod.FlowResult,
        temporal_detector: str,
        temporal_code: str,
        temporal_accounts: tuple[str, ...],
        coverage_members: tuple[str, ...],
        has_downstream: bool,
        features: dict[str, Any],
        indicators: list[ContextIndicator],
        claim_dependents: tuple[str, ...] = (),
    ) -> None:
        temporal_ev = self._temporal_evidence(fid, flow, temporal_accounts, temporal_code)
        if temporal_detector != flow_mod.DETECTOR_ID:
            temporal_ev = replace(temporal_ev, detector_version=str(self.config.detectors[kind]["detector_version"]))
        all_tx = sorted(set(struct_ev.transaction_ids) | set(temporal_ev.transaction_ids))
        dates = [self.snapshot.transfers[t].observed_date for t in all_tx]
        coverage = assess_coverage(
            kind=kind,
            subject_account_id=subject,
            member_ids=coverage_members,
            entry_ids=entry_ids,
            has_downstream=has_downstream,
            transfers=self._transfers(all_tx),
            flow=flow,
            contract=self.contract,
            window=(min(dates), max(dates)),
            claim_dependents=claim_dependents,
        )
        cov_ev = self._coverage_evidence(fid, coverage, detector_version)
        struct_sig = Signal(
            id=stable_uuid("signal", fid, detector_id),
            formation_id=fid,
            family="STRUCTURE",
            detector_id=detector_id,
            detector_version=detector_version,
            status="supported",
            strength=struct_strength,
            evidence_ids=(struct_ev.id,),
            limitations=("structural_only",),
            dependency_tags=struct_tags,
        )
        temporal_sig = self._temporal_signal(fid, flow, temporal_ev.id, temporal_detector)
        formation = Formation(
            id=fid,
            kind=kind,  # type: ignore[arg-type]
            currency=cg.currency,
            subject_account_id=subject,
            member_ids=members,
            entry_ids=entry_ids,
            exit_ids=exit_ids,
            features=features,
            limitations=coverage.limitations,
            detector_id=detector_id,
            detector_version=detector_version,
            window_start=min(dates),
            window_end=max(dates),
            transaction_ids=tuple(all_tx),
        )
        reasons = [struct_reason, _flow_reason(flow, temporal_code), *self._coverage_reasons(coverage, subject)]
        self._publish(
            formation,
            [struct_ev, temporal_ev, cov_ev, *self._context_evidence(fid, indicators)],
            [struct_sig, temporal_sig],
            coverage,
            reasons,
            tuple(i.code for i in indicators),
        )

    # -- detectors ---------------------------------------------------------------
    def funnels(self, cg: CurrencyGraph) -> None:
        fcfg = self.config.detectors["funnel"]
        tcfg = self.config.detectors["temporal"]
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
            flow = flow_mod.layered_flow(
                [self._transfers(entry_tx), self._transfers(out_tx)],
                max_lag_days=int(tcfg["max_hop_lag_days"]),
                min_compatible_fraction=str(tcfg["min_compatible_fraction"]),
                max_transfers=int(tcfg["max_transfers"]),
            )
            flow = self._attributed(
                flow, attribution.consolidation_pro_rata(cg, cand.center, cand.total_incoming_minor)
            )
            struct_ev = Evidence(
                id=stable_uuid("evidence", fid, "structure"),
                kind="graph_fact",
                reason_code="STRUCT_FUNNEL_FEEDERS",
                subject_id=fid,
                transaction_ids=tuple(sorted(entry_tx)),
                account_ids=members,
                observations={
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
                },
                thresholds={
                    "min_feeders": int(fcfg["min_feeders"]),
                    "min_feeder_share": str(fcfg["min_feeder_share"]),
                    "min_incoming_minor": str(fcfg["min_incoming_minor"]),
                },
                limitations=("structural_only",),
                detector_version=str(fcfg["detector_version"]),
            )
            self._emit(
                cg=cg,
                kind="funnel",
                fid=fid,
                detector_id=funnel_mod.DETECTOR_ID,
                detector_version=str(fcfg["detector_version"]),
                subject=cand.center,
                members=members,
                entry_ids=feeders,
                exit_ids=cand.downstream,
                struct_ev=struct_ev,
                struct_strength=self._structure_strength(
                    fcfg, len(cand.feeders), int(fcfg["min_feeders"]), [f.share_bp for f in cand.feeders]
                ),
                struct_tags=("graph.in_degree", "graph.edge_share"),
                struct_reason=ReasonCode(
                    "STRUCT_FUNNEL_FEEDERS",
                    {
                        "count": len(cand.feeders),
                        "total_minor": _money(cand.total_incoming_minor),
                        "currency": cg.currency,
                    },
                ),
                flow=flow,
                temporal_detector=flow_mod.DETECTOR_ID,
                temporal_code="TEMPORAL_PASS_THROUGH_SUPPORTED",
                temporal_accounts=(cand.center, *cand.downstream),
                coverage_members=(*members, *cand.downstream),
                has_downstream=bool(cand.downstream),
                features={
                    "feeder_count": len(cand.feeders),
                    "incoming_minor": _money(cand.total_incoming_minor),
                    "downstream_count": len(cand.downstream),
                    "temporal_status": flow.status,
                },
                indicators=self._context(cg, cand.center, feeders, "in"),
            )

    def chains(self, cg: CurrencyGraph) -> None:
        ccfg = self.config.detectors["chain"]
        tcfg = self.config.detectors["temporal"]
        detection = chain_mod.detect_chains(cg, ccfg)
        if detection.budget_exceeded:
            self.out.partial_reasons.append(f"path_budget_exceeded:{cg.currency}")
        for cand in detection.candidates:
            path = cand.path
            fid = stable_uuid("formation", self.snapshot_id, "chain", cg.currency, *path)
            hop_tx = [list(cg.edges[(path[i], path[i + 1])].transaction_ids) for i in range(cand.hops)]
            flow = flow_mod.layered_flow(
                [self._transfers(h) for h in hop_tx],
                max_lag_days=int(tcfg["max_hop_lag_days"]),
                min_compatible_fraction=str(tcfg["min_compatible_fraction"]),
                max_transfers=int(tcfg["max_transfers"]),
            )
            flow = self._attributed(flow, attribution.path_pro_rata(cg, path))
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
                cg=cg,
                kind="chain",
                fid=fid,
                detector_id=chain_mod.DETECTOR_ID,
                detector_version=str(ccfg["detector_version"]),
                subject=path[-1],
                members=path,
                entry_ids=(path[0],),
                exit_ids=(path[-1],),
                struct_ev=struct_ev,
                struct_strength=chain_mod.chain_strength(cand.hops, int(ccfg["min_hops"])),
                struct_tags=("graph.path",),
                struct_reason=ReasonCode("STRUCT_CHAIN_PATH", {"hops": cand.hops, "currency": cg.currency}),
                flow=flow,
                temporal_detector=flow_mod.DETECTOR_ID,
                temporal_code="TEMPORAL_PATH_SUPPORTED",
                temporal_accounts=path,
                coverage_members=path,
                has_downstream=True,
                features={"hops": cand.hops, "entry_minor": _money(flow.entry_minor), "temporal_status": flow.status},
                indicators=[],
            )

    def fanouts(self, cg: CurrencyGraph) -> None:
        fcfg = self.config.detectors["fanout"]
        tcfg = self.config.detectors["temporal"]
        for cand in fanout_mod.detect_fanouts(cg, fcfg):
            recipients = tuple(r.account_id for r in cand.recipients)
            members = (cand.source, *recipients)
            fid = stable_uuid("formation", self.snapshot_id, "fanout", cg.currency, cand.source, *sorted(recipients))
            out_tx = [t for r in cand.recipients for t in r.transaction_ids]
            onward_tx = [
                tid
                for r in recipients
                for (snd, rcv), e in sorted(cg.edges.items())
                if snd == r and rcv not in (r, cand.source)
                for tid in e.transaction_ids
            ]
            flow = flow_mod.layered_flow(
                [self._transfers(out_tx), self._transfers(onward_tx)],
                max_lag_days=int(tcfg["max_hop_lag_days"]),
                min_compatible_fraction=str(tcfg["min_compatible_fraction"]),
                max_transfers=int(tcfg["max_transfers"]),
            )
            flow = self._attributed(flow, attribution.distribution_pro_rata(cg, cand.source, recipients))
            struct_ev = Evidence(
                id=stable_uuid("evidence", fid, "structure"),
                kind="graph_fact",
                reason_code="STRUCT_FANOUT_RECIPIENTS",
                subject_id=fid,
                transaction_ids=tuple(sorted(out_tx)),
                account_ids=members,
                observations={
                    "source": cand.source,
                    "recipient_count": len(recipients),
                    "total_minor": _money(cand.total_outgoing_minor),
                    "currency": cg.currency,
                    "recipients": [
                        {
                            "account_id": r.account_id,
                            "edge_minor": _money(r.edge_minor),
                            "recipient_incoming_minor": _money(r.recipient_incoming_minor),
                            "share_bp": r.share_bp,
                            "transaction_count": len(r.transaction_ids),
                        }
                        for r in cand.recipients
                    ],
                    "upstream_accounts": list(cand.upstream),
                },
                thresholds={
                    "min_recipients": int(fcfg["min_recipients"]),
                    "min_recipient_share": str(fcfg["min_recipient_share"]),
                    "min_outgoing_minor": str(fcfg["min_outgoing_minor"]),
                },
                limitations=("structural_only",),
                detector_version=str(fcfg["detector_version"]),
            )
            strength_cfg = {**fcfg, "min_feeder_share": fcfg["min_recipient_share"]}
            self._emit(
                cg=cg,
                kind="fanout",
                fid=fid,
                detector_id=fanout_mod.DETECTOR_ID,
                detector_version=str(fcfg["detector_version"]),
                subject=cand.source,
                members=members,
                entry_ids=(cand.source,),
                exit_ids=recipients,
                struct_ev=struct_ev,
                struct_strength=self._structure_strength(
                    strength_cfg, len(recipients), int(fcfg["min_recipients"]), [r.share_bp for r in cand.recipients]
                ),
                struct_tags=("graph.out_degree", "graph.edge_share"),
                struct_reason=ReasonCode(
                    "STRUCT_FANOUT_RECIPIENTS",
                    {
                        "count": len(recipients),
                        "total_minor": _money(cand.total_outgoing_minor),
                        "currency": cg.currency,
                    },
                ),
                flow=flow,
                temporal_detector=flow_mod.DETECTOR_ID,
                temporal_code="TEMPORAL_ONWARD_SUPPORTED",
                temporal_accounts=recipients,
                coverage_members=members,
                has_downstream=True,
                features={
                    "recipient_count": len(recipients),
                    "outgoing_minor": _money(cand.total_outgoing_minor),
                    "temporal_status": flow.status,
                },
                indicators=self._context(cg, cand.source, recipients, "out"),
                claim_dependents=recipients,
            )

    def cycles(self, cg: CurrencyGraph) -> None:
        ycfg = self.config.detectors["cycle"]
        tcfg = self.config.detectors["temporal"]
        detection = cycle_mod.detect_cycles(cg, ycfg)
        if detection.budget_exceeded:
            self.out.partial_reasons.append(f"cycle_budget_exceeded:{cg.currency}")
        for cycle in detection.cycles:
            k = len(cycle)
            fid = stable_uuid("formation", self.snapshot_id, "cycle", cg.currency, *cycle)
            leg_tx = [list(cg.edges[(cycle[i], cycle[(i + 1) % k])].transaction_ids) for i in range(k)]
            flow = episodes_mod.cycle_episodes(
                [self._transfers(h) for h in leg_tx],
                max_lag_days=int(tcfg["max_hop_lag_days"]),
                leg_amount_min_ratio=str(ycfg["leg_amount_min_ratio"]),
                leg_amount_max_ratio=str(ycfg["leg_amount_max_ratio"]),
                min_episodes=int(ycfg["min_episodes"]),
            )
            struct_tx = sorted(t for h in leg_tx for t in h)
            n_episodes = len(flow.supporting_transaction_ids) // k
            struct_ev = Evidence(
                id=stable_uuid("evidence", fid, "structure"),
                kind="graph_fact",
                reason_code="STRUCT_CYCLE",
                subject_id=fid,
                transaction_ids=tuple(struct_tx),
                account_ids=cycle,
                observations={
                    "cycle": list(cycle),
                    "length": k,
                    "currency": cg.currency,
                    "total_minor": _money(sum(self.snapshot.transfers[t].amount_minor for t in struct_tx)),
                    "leg_edges": [
                        {
                            "sender": cycle[i],
                            "receiver": cycle[(i + 1) % k],
                            "edge_minor": _money(cg.edges[(cycle[i], cycle[(i + 1) % k])].amount_minor),
                            "transaction_count": len(leg_tx[i]),
                        }
                        for i in range(k)
                    ],
                },
                thresholds={
                    "min_length": int(ycfg["min_length"]),
                    "max_length": int(ycfg["max_length"]),
                    "min_edge_minor": str(ycfg["min_edge_minor"]),
                },
                limitations=("structural_only", "cycle_does_not_prove_round_trip"),
                detector_version=str(ycfg["detector_version"]),
            )
            self._emit(
                cg=cg,
                kind="cycle",
                fid=fid,
                detector_id=cycle_mod.DETECTOR_ID,
                detector_version=str(ycfg["detector_version"]),
                subject=cycle[0],
                members=cycle,
                entry_ids=(cycle[0],),
                exit_ids=(cycle[0],),
                struct_ev=struct_ev,
                struct_strength=0.6,
                struct_tags=("graph.cycle",),
                struct_reason=ReasonCode("STRUCT_CYCLE", {"length": k, "currency": cg.currency}),
                flow=flow,
                temporal_detector=episodes_mod.DETECTOR_ID,
                temporal_code="TEMPORAL_ROUND_TRIPS_SUPPORTED",
                temporal_accounts=cycle,
                coverage_members=cycle,
                has_downstream=True,
                features={"length": k, "episodes": n_episodes, "temporal_status": flow.status},
                indicators=[],
            )


def run_analysis(
    *, dataset_id: str, transfers: list[ObservedTransfer], contract: dict[str, Any], config: AnalysisConfig
) -> AnalysisOutput:
    snapshot = build_snapshot(transfers)
    builder = _Builder(dataset_id, snapshot, config, contract)
    for currency in snapshot.currencies:
        cg = snapshot.by_currency[currency]
        builder.funnels(cg)
        builder.chains(cg)
        if "fanout" in config.detectors:
            builder.fanouts(cg)
        if "cycle" in config.detectors:
            builder.cycles(cg)
    out = builder.out
    out.formations.sort(key=lambda f: f.id)
    out.evidence.sort(key=lambda e: e.id)
    out.signals.sort(key=lambda s: s.id)
    out.assessments.sort(key=lambda a: a.id)
    return out
