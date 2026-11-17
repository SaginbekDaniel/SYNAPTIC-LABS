"""Funnel / consolidation detector (spec §9.1, RULE_FNL_001).

A centre ``c`` qualifies when at least ``min_feeders`` distinct senders route at least
``min_feeder_share`` of their *observed* outgoing volume (same currency) to ``c`` and the
qualifying feeders' total reaches ``min_incoming_minor``. Feeder count alone is not
treated as proof: payroll, marketplace and settlement hubs share this structure, which
is why structural strength is capped and temporal corroboration is evaluated separately.

``funnel-v2`` (``exclude_returning_feeders``): a sender that the centre itself paid
earlier — at least ``returning_min_ratio`` of what the sender later returns, with the
centre's first payment no later than the sender's last transfer back — is *returning*
funds (loan instalments, reimbursements), not consolidating an independent source. Such
senders are reported as ``returning_feeders`` but do not count towards ``min_feeders``.
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
    returning_feeders: tuple[str, ...] = ()

    @property
    def total_incoming_minor(self) -> int:
        return sum(f.edge_minor for f in self.feeders)


def detect_funnels(cg: CurrencyGraph, cfg: dict[str, Any]) -> list[FunnelCandidate]:
    min_feeders = int(cfg["min_feeders"])
    min_share = Fraction(str(cfg["min_feeder_share"]))
    min_incoming = int(cfg["min_incoming_minor"])
    exclude_returning = bool(cfg.get("exclude_returning_feeders", False))
    returning_ratio = Fraction(str(cfg.get("returning_min_ratio", "0.1")))
    out: list[FunnelCandidate] = []
    for center in sorted(cg.graph.nodes):
        feeders: list[FeederEdge] = []
        returning: list[str] = []
        for sender in sorted(cg.graph.predecessors(center)):
            if sender == center:
                continue
            edge = cg.edges[(sender, center)]
            sender_out = cg.metrics[sender].outgoing_minor
            if sender_out <= 0:
                continue
            if Fraction(edge.amount_minor, sender_out) >= min_share:
                back = cg.edges.get((center, sender))
                if (
                    exclude_returning
                    and back is not None
                    and back.first_date <= edge.last_date
                    and Fraction(back.amount_minor, edge.amount_minor) >= returning_ratio
                ):
                    returning.append(sender)
                    continue
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
        out.append(
            FunnelCandidate(
                center=center, feeders=tuple(feeders), downstream=downstream, returning_feeders=tuple(returning)
            )
        )
    return out


def funnel_strength(n_feeders: int, min_feeders: int) -> float:
    """Documented heuristic: 0.6 at the threshold, rising linearly to 1.0 at 2x threshold."""
    excess = max(0, n_feeders - min_feeders)
    return round(0.6 + 0.4 * min(1.0, excess / max(1, min_feeders)), 4)
