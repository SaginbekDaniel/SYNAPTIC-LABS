"""Funnel / consolidation detector (spec §9.1, RULE_FNL_001).

A centre ``c`` qualifies when at least ``min_feeders`` distinct senders route at least
``min_feeder_share`` of their *observed* outgoing volume (same currency) to ``c`` and the
qualifying feeders' total reaches ``min_incoming_minor``. Feeder count alone is not
treated as proof: payroll, marketplace and settlement hubs share this structure, which
is why structural strength is capped and temporal corroboration is evaluated separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from nexora.analytics.graph_builder import CurrencyGraph

DETECTOR_ID = "structural.funnel"


@dataclass(frozen=True)
class FeederEdge:
    account_id: str
    edge_minor: int
    sender_outgoing_minor: int
    transaction_ids: tuple[str, ...]

    @property
    def share_bp(self) -> int:
        return self.edge_minor * 10_000 // self.sender_outgoing_minor


@dataclass(frozen=True)
class FunnelCandidate:
    center: str
    feeders: tuple[FeederEdge, ...]
    downstream: tuple[str, ...]

    @property
    def total_incoming_minor(self) -> int:
        return sum(f.edge_minor for f in self.feeders)


def detect_funnels(cg: CurrencyGraph, cfg: dict[str, Any]) -> list[FunnelCandidate]:
    min_feeders = int(cfg["min_feeders"])
    min_share = Fraction(str(cfg["min_feeder_share"]))
    min_incoming = int(cfg["min_incoming_minor"])
    out: list[FunnelCandidate] = []
    for center in sorted(cg.graph.nodes):
        feeders: list[FeederEdge] = []
        for sender in sorted(cg.graph.predecessors(center)):
            if sender == center:
                continue
            edge = cg.edges[(sender, center)]
            sender_out = cg.metrics[sender].outgoing_minor
            if sender_out <= 0:
                continue
            if Fraction(edge.amount_minor, sender_out) >= min_share:
                feeders.append(
                    FeederEdge(
                        account_id=sender,
                        edge_minor=edge.amount_minor,
                        sender_outgoing_minor=sender_out,
                        transaction_ids=edge.transaction_ids,
                    )
                )
        if len(feeders) < min_feeders:
            continue
        if sum(f.edge_minor for f in feeders) < min_incoming:
            continue
        downstream = tuple(sorted(r for r in cg.graph.successors(center) if r != center))
        out.append(FunnelCandidate(center=center, feeders=tuple(feeders), downstream=downstream))
    return out


def funnel_strength(n_feeders: int, min_feeders: int) -> float:
    """Documented heuristic: 0.6 at the threshold, rising linearly to 1.0 at 2x threshold."""
    excess = max(0, n_feeders - min_feeders)
    return round(0.6 + 0.4 * min(1.0, excess / max(1, min_feeders)), 4)


def dedication_strength(shares_bp: list[int], min_share: str) -> float:
    """Strength from how *dedicated* the counterparties are, not how many there are.

    0.6 when the median counterparty routes exactly ``min_share`` of its observed flow through
    the subject, rising linearly to 1.0 when it routes all of it. Feeder count measures scale,
    which legitimate processors, billers and employers have more of than mule collectors.
    """
    from statistics import median

    lo = Fraction(min_share)
    med = Fraction(int(median(shares_bp)), 10_000) if shares_bp else lo
    if lo >= 1:
        return 1.0
    return round(float(Fraction(6, 10) + Fraction(4, 10) * max(Fraction(0), (med - lo) / (1 - lo))), 4)
