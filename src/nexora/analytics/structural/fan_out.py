"""Fan-out / coordinated-distribution detector (spec §8.2, AML typology "fan-out").

A distributor ``d`` qualifies when at least ``min_recipients`` distinct receivers obtain
at least ``min_recipient_share`` of their *observed* incoming volume (same currency) from
``d`` and the qualifying outflow reaches ``min_outgoing_minor``.

The structure alone is shared by payroll, supplier runs and remittances, so structural
strength is capped and the decision is left to temporal corroboration (was the money
distributed shortly after it arrived?) and peer statistics.

``exclude_returning_recipients`` mirrors the funnel rule: a receiver that later sends at
least ``returning_min_ratio`` of what it received back to the distributor (loan
instalments, reimbursements) is in a two-way relationship, not a one-way dispersal. Such
receivers are reported as ``returning_recipients`` and do not count towards the minimum.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from nexora.analytics.graph_builder import CurrencyGraph

DETECTOR_ID = "structural.fan_out"


@dataclass(frozen=True)
class RecipientEdge:
    account_id: str
    edge_minor: int
    receiver_incoming_minor: int
    transaction_ids: tuple[str, ...]
    forwards_onward: bool

    @property
    def share_bp(self) -> int:
        return self.edge_minor * 10_000 // self.receiver_incoming_minor


@dataclass(frozen=True)
class FanOutCandidate:
    distributor: str
    recipients: tuple[RecipientEdge, ...]
    sources: tuple[str, ...]
    returning_recipients: tuple[str, ...] = ()

    @property
    def total_outgoing_minor(self) -> int:
        return sum(r.edge_minor for r in self.recipients)

    @property
    def onward_count(self) -> int:
        return sum(1 for r in self.recipients if r.forwards_onward)


def detect_fan_outs(cg: CurrencyGraph, cfg: dict[str, Any]) -> list[FanOutCandidate]:
    min_recipients = int(cfg["min_recipients"])
    min_share = Fraction(str(cfg["min_recipient_share"]))
    min_outgoing = int(cfg["min_outgoing_minor"])
    exclude_returning = bool(cfg.get("exclude_returning_recipients", False))
    returning_ratio = Fraction(str(cfg.get("returning_min_ratio", "0.1")))
    out: list[FanOutCandidate] = []
    for dist in sorted(cg.graph.nodes):
        recipients: list[RecipientEdge] = []
        returning: list[str] = []
        for rcv in sorted(cg.graph.successors(dist)):
            if rcv == dist:
                continue
            edge = cg.edges[(dist, rcv)]
            rcv_in = cg.metrics[rcv].incoming_minor
            if rcv_in <= 0 or Fraction(edge.amount_minor, rcv_in) < min_share:
                continue
            back = cg.edges.get((rcv, dist))
            if (
                exclude_returning
                and back is not None
                and back.last_date >= edge.first_date
                and Fraction(back.amount_minor, edge.amount_minor) >= returning_ratio
            ):
                returning.append(rcv)
                continue
            recipients.append(
                RecipientEdge(
                    account_id=rcv,
                    edge_minor=edge.amount_minor,
                    receiver_incoming_minor=rcv_in,
                    transaction_ids=edge.transaction_ids,
                    forwards_onward=cg.metrics[rcv].out_degree > 0,
                )
            )
        if len(recipients) < min_recipients:
            continue
        if sum(r.edge_minor for r in recipients) < min_outgoing:
            continue
        sources = tuple(sorted(s for s in cg.graph.predecessors(dist) if s != dist))
        out.append(
            FanOutCandidate(
                distributor=dist, recipients=tuple(recipients), sources=sources, returning_recipients=tuple(returning)
            )
        )
    return out


def fan_out_strength(n_recipients: int, min_recipients: int) -> float:
    """Documented heuristic, same shape as the funnel: 0.6 at the threshold, 1.0 at 2x."""
    excess = max(0, n_recipients - min_recipients)
    return round(0.6 + 0.4 * min(1.0, excess / max(1, min_recipients)), 4)
