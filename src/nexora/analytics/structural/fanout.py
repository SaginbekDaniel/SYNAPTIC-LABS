"""Fan-out / distribution detector (spec §9.2).

Mirror of the funnel: a source ``s`` qualifies when at least ``min_recipients`` distinct
receivers obtain at least ``min_recipient_share`` of their *observed* incoming volume (same
currency) from ``s`` and the dispersed total reaches ``min_outgoing_minor``. Distinct receiver
ids are counted, never individual transfers.

Payroll, payouts and family support share this structure; whether the recipients move the
money onwards is decided by the temporal engine, and benign context by ``analytics.context``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from nexora.analytics.graph_builder import CurrencyGraph

DETECTOR_ID = "structural.fanout"


@dataclass(frozen=True)
class RecipientEdge:
    account_id: str
    edge_minor: int
    recipient_incoming_minor: int
    transaction_ids: tuple[str, ...]

    @property
    def share_bp(self) -> int:
        return self.edge_minor * 10_000 // self.recipient_incoming_minor


@dataclass(frozen=True)
class FanoutCandidate:
    source: str
    recipients: tuple[RecipientEdge, ...]
    upstream: tuple[str, ...]

    @property
    def total_outgoing_minor(self) -> int:
        return sum(r.edge_minor for r in self.recipients)


def detect_fanouts(cg: CurrencyGraph, cfg: dict[str, Any]) -> list[FanoutCandidate]:
    min_recipients = int(cfg["min_recipients"])
    min_share = Fraction(str(cfg["min_recipient_share"]))
    min_outgoing = int(cfg["min_outgoing_minor"])
    out: list[FanoutCandidate] = []
    for source in sorted(cg.graph.nodes):
        recipients: list[RecipientEdge] = []
        for r in sorted(cg.graph.successors(source)):
            if r == source:
                continue
            incoming = cg.metrics[r].incoming_minor
            edge = cg.edges[(source, r)]
            if incoming > 0 and Fraction(edge.amount_minor, incoming) >= min_share:
                recipients.append(RecipientEdge(r, edge.amount_minor, incoming, edge.transaction_ids))
        if len(recipients) < min_recipients or sum(r.edge_minor for r in recipients) < min_outgoing:
            continue
        upstream = tuple(sorted(p for p in cg.graph.predecessors(source) if p != source))
        out.append(FanoutCandidate(source=source, recipients=tuple(recipients), upstream=upstream))
    return out
