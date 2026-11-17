"""Circular-flow (round-tripping) candidate detector (spec §8.2).

Finds simple directed cycles of ``min_length..max_length`` accounts in the aggregated
graph where every member is a low-degree pass-through account, every edge meets a
materiality floor and consecutive edge volumes stay within ``hop_amount_min_ratio``.

A graph cycle is *not* evidence that money went round: the temporal engine checks
whether a time-respecting sequence of transfers closes the loop. Enumeration is
bounded and fails closed (``cycle_budget_exceeded``) instead of hanging.

The canonical rotation starts at the member whose outgoing cycle edge carries the
earliest transfer, so the temporal layers follow observed chronology.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import Any

import networkx as nx

from nexora.analytics.graph_builder import CurrencyGraph

DETECTOR_ID = "structural.cycle"


@dataclass(frozen=True)
class CycleCandidate:
    members: tuple[str, ...]  # rotation order; the edge members[-1] -> members[0] closes the loop

    @property
    def length(self) -> int:
        return len(self.members)

    def edges(self) -> list[tuple[str, str]]:
        n = len(self.members)
        return [(self.members[i], self.members[(i + 1) % n]) for i in range(n)]


@dataclass(frozen=True)
class CycleDetection:
    candidates: tuple[CycleCandidate, ...]
    budget_exceeded: bool


def _canonical(cg: CurrencyGraph, cycle: list[str]) -> tuple[str, ...]:
    n = len(cycle)

    def start_key(i: int) -> tuple[str, str]:
        edge = cg.edges[(cycle[i], cycle[(i + 1) % n])]
        return (edge.first_date.isoformat(), cycle[i])

    start = min(range(n), key=start_key)
    return tuple(cycle[start:] + cycle[:start])


def detect_cycles(cg: CurrencyGraph, cfg: dict[str, Any]) -> CycleDetection:
    min_len = int(cfg["min_length"])
    max_len = int(cfg["max_length"])
    max_degree = int(cfg["member_max_degree"])
    min_edge = int(cfg["min_edge_minor"])
    hop_ratio = Fraction(str(cfg["hop_amount_min_ratio"]))
    max_cycles = int(cfg["max_cycles"])

    members = {
        n
        for n, m in cg.metrics.items()
        if 1 <= m.in_degree <= max_degree and 1 <= m.out_degree <= max_degree and n in cg.graph
    }
    sub = nx.DiGraph()
    sub.add_nodes_from(sorted(members))
    for (u, v), e in sorted(cg.edges.items()):
        if u in members and v in members and e.amount_minor >= min_edge:
            sub.add_edge(u, v)

    found: set[tuple[str, ...]] = set()
    exceeded = False
    for cycle in nx.simple_cycles(sub, length_bound=max_len):
        if len(cycle) < min_len:
            continue
        canon = _canonical(cg, list(cycle))
        amounts = [cg.edges[e].amount_minor for e in CycleCandidate(canon).edges()]
        # every consecutive pair, including the closing edge back to the start
        if any(Fraction(min(a, b), max(a, b)) < hop_ratio for a, b in pairwise([*amounts, amounts[0]])):
            continue
        if len(found) >= max_cycles:
            exceeded = True  # reported as a partial snapshot, like the chain path budget
            break
        found.add(canon)
    return CycleDetection(candidates=tuple(CycleCandidate(c) for c in sorted(found)), budget_exceeded=exceeded)


def cycle_strength(length: int, min_length: int) -> float:
    """Documented heuristic: 0.6 at the minimum length, +0.1 per extra member, capped at 0.8.

    Longer loops are harder to form by coincidence, but a closed loop of pass-through
    accounts is still only a structure; temporal corroboration carries the rest.
    """
    return round(min(0.8, 0.6 + 0.1 * max(0, length - min_length)), 4)
