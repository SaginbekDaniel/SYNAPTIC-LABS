"""Correlation-aware triage priority (spec §14), policy ``risk-policy-v1``.

* One structural signal per formation: overlapping structural views of the same
  topology are never added as independent confirmations.
* Missing families contribute zero and are listed; weights are not renormalised.
* Evidence gates cap the band (contradicted / ambiguous / unavailable chronology).
* Subject coverage limitations (e.g. collection boundary) force abstention:
  ``insufficient_evidence`` with no numeric priority.
"""

from __future__ import annotations

from typing import Any

from nexora.domain.analysis import BAND_ORDER, Band, CoverageAssessment, ReasonCode, RiskAssessment, Signal
from nexora.domain.ids import stable_uuid


def _cap(band: str, cap: str) -> str:
    return band if BAND_ORDER.index(band) <= BAND_ORDER.index(cap) else cap


def assess(
    *,
    formation_id: str,
    signals: list[Signal],
    coverage: CoverageAssessment,
    reasons: list[ReasonCode],
    policy: dict[str, Any],
    policy_sha256: str,
) -> RiskAssessment:
    weights: dict[str, float] = {k: float(v) for k, v in policy["family_weights"].items()}
    by_family: dict[str, Signal] = {}
    for s in sorted(signals, key=lambda s: (s.family, -(s.strength or 0.0), s.id)):
        # Correlation guard: at most one (the strongest) credited signal per family.
        by_family.setdefault(s.family, s)

    supported = sorted(
        f for f, s in by_family.items() if s.status == "supported" and s.strength is not None and s.strength > 0
    )
    missing = sorted(f for f in weights if f not in by_family or by_family[f].status == "unavailable")
    reason_list = list(reasons)
    rid = stable_uuid("risk", formation_id, policy_sha256)
    signal_ids = tuple(s.id for s in sorted(signals, key=lambda s: s.id))

    blocking = [lim for lim in coverage.subject_limitations if lim in set(policy["abstain_on_subject_limitations"])]
    if blocking or not supported:
        if not supported:
            reason_list.append(ReasonCode("NO_SUPPORTED_SIGNAL"))
        return RiskAssessment(
            id=rid,
            formation_id=formation_id,
            policy_version=str(policy["version"]),
            policy_sha256=policy_sha256,
            priority=None,
            band="insufficient_evidence",
            signal_ids=signal_ids,
            supported_families=tuple(supported),
            missing_families=tuple(missing),
            coverage=coverage,
            reason_codes=tuple(reason_list),
        )

    score = 0.0
    for family, signal in by_family.items():
        if signal.strength is not None:
            score += weights.get(family, 0.0) * signal.strength
    priority = max(0, min(100, round(score * 100)))

    band = "low"
    for name in ("critical", "high", "medium", "low"):
        rule = policy["bands"][name]
        if priority >= int(rule["min_priority"]) and len(supported) >= int(rule["min_supported_families"]):
            band = name
            break

    temporal = by_family.get("TEMPORAL")
    caps = policy["caps"]
    gates: list[str] = []
    if temporal is None or temporal.status == "unavailable":
        gates.append("temporal_unavailable")
    elif temporal.status == "contradicted":
        gates.append("temporal_contradicted")
    elif temporal.status == "possible_ambiguous":
        gates.append("temporal_ambiguous")
    peer = by_family.get("PEER_STATISTICS")
    if peer is not None and peer.status == "contradicted" and "peer_contradicted" in caps:
        # Counter-evidence: the subject's turnover is no more time-concentrated than its peers'.
        gates.append("peer_contradicted")
    capped = band
    applied: list[str] = []
    for gate in gates:
        new_band = _cap(capped, caps[gate])
        if new_band != capped:
            applied.append(gate)
        capped = new_band
    if capped != band:
        reason_list.append(ReasonCode("BAND_CAPPED_BY_EVIDENCE", {"from": band, "to": capped, "gates": applied}))
    if len(supported) < 2:
        reason_list.append(ReasonCode("NO_INDEPENDENT_CORROBORATION", {"supported_families": supported}))

    final_band: Band = capped  # type: ignore[assignment]
    return RiskAssessment(
        id=rid,
        formation_id=formation_id,
        policy_version=str(policy["version"]),
        policy_sha256=policy_sha256,
        priority=priority,
        band=final_band,
        signal_ids=signal_ids,
        supported_families=tuple(supported),
        missing_families=tuple(missing),
        coverage=coverage,
        reason_codes=tuple(reason_list),
    )


def opens_alert(band: str, policy: dict[str, Any]) -> bool:
    if band == "insufficient_evidence":
        return True  # unresolved cases remain visible for review ("watch")
    return BAND_ORDER.index(band) >= BAND_ORDER.index(str(policy["alert_min_band"]))
