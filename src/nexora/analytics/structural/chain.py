"""Layering-chain candidate detector (spec §9.3).

Structural prerequisites: every hop meets a materiality floor, every intermediary is a
low-degree pass-through account, and consecutive hop volumes stay within
``hop_amount_min_ratio`` of each other (layered funds keep a similar size).

Returns *structural* path candidates only: a path existing in the aggregated graph does
not show that the same funds traversed it — the temporal engine decides that. Path
enumeration is bounded; on budget exhaustion the detector fails closed with
``path_budget_exceeded`` instead of hanging.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from nexora.analytics.graph_builder import CurrencyGraph

DETECTOR_ID = "structural.chain"


@dataclass(frozen=True)
class ChainCandidate:
    path: tuple[str, ...]

    @property
    def hops(self) -> int:
        return len(self.path) - 1


@dataclass(frozen=True)
class ChainDetection:
    candidates: tuple[ChainCandidate, ...]
    budget_exceeded: bool
    expansions: int


def _is_intermediary(cg: CurrencyGraph, node: str, max_degree: int, min_ratio: Fraction) -> bool:
    m = cg.metrics[node]
    if m.in_degree < 1 or m.out_degree < 1:
        return False
    if m.in_degree > max_degree or m.out_degree > max_degree:
        return False
    lo, hi = sorted((m.incoming_minor, m.outgoing_minor))
    return hi > 0 and Fraction(lo, hi) >= min_ratio


def detect_chains(cg: CurrencyGraph, cfg: dict[str, Any]) -> ChainDetection:
    min_hops = int(cfg["min_hops"])
    max_hops = int(cfg["max_hops"])
    max_degree = int(cfg["intermediary_max_degree"])
    min_ratio = Fraction(str(cfg["pass_through_min_ratio"]))
    min_edge = int(cfg["min_edge_minor"])
    hop_ratio = Fraction(str(cfg["hop_amount_min_ratio"]))
    max_paths = int(cfg["max_paths"])
    max_expansions = int(cfg["max_expansions"])

    g = cg.graph
    intermediaries = {n for n in g.nodes if _is_intermediary(cg, n, max_degree, min_ratio)}

    def eligible(u: str, v: str) -> bool:
        return u != v and cg.edges[(u, v)].amount_minor >= min_edge

    def consistent(prev: tuple[str, str], nxt: tuple[str, str]) -> bool:
        lo, hi = sorted((cg.edges[prev].amount_minor, cg.edges[nxt].amount_minor))
        return Fraction(lo, hi) >= hop_ratio

    found: list[tuple[str, ...]] = []
    expansions = 0
    exceeded = False

    def extend(path: list[str]) -> None:
        nonlocal expansions, exceeded
        if exceeded:
            return
        for nxt in sorted(g.successors(path[-1])):
            if nxt in path or not eligible(path[-1], nxt):
                continue
            if not consistent((path[-2], path[-1]), (path[-1], nxt)):
                continue
            expansions += 1
            if expansions > max_expansions or len(found) >= max_paths:
                exceeded = True
                return
            new_path = [*path, nxt]
            hops = len(new_path) - 1
            if hops >= min_hops:
                found.append(tuple(new_path))
            if nxt in intermediaries and hops < max_hops:
                extend(new_path)
            if exceeded:
                return

    for start in sorted(g.nodes):
        for first in sorted(g.successors(start)):
            if first in intermediaries and eligible(start, first):
                extend([start, first])
                if exceeded:
                    break
        if exceeded:
            break

    # Keep maximal paths only: drop any path that is a contiguous sub-path of another.
    unique = sorted(set(found))
    dominated: set[tuple[str, ...]] = set()
    for p in unique:
        n = len(p)
        for i in range(n):
            for j in range(i + min_hops + 1, n + 1):
                sub = p[i:j]
                if sub != p:
                    dominated.add(sub)
    candidates = tuple(ChainCandidate(path=p) for p in unique if p not in dominated)
    return ChainDetection(candidates=candidates, budget_exceeded=exceeded, expansions=expansions)


def chain_strength(hops: int, min_hops: int) -> float:
    """Documented heuristic: 0.6 at the minimum length, +0.2 per extra hop, capped at 1.0."""
    return round(min(1.0, 0.6 + 0.2 * max(0, hops - min_hops)), 4)
