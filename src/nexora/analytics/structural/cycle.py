"""Circular-flow detector (spec §9.4): short directed cycles, bounded enumeration.

Cycles are enumerated once each in canonical rotation (the smallest account id first, all other
members larger), so rotations are never reported twice. Only edges meeting ``min_edge_minor``
are followed. Enumeration fails closed with ``cycle_budget_exceeded``.

A structural cycle says nothing about whether value actually went round; repeated,
time-respecting and amount-consistent round trips are verified by ``temporal.episodes``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexora.analytics.graph_builder import CurrencyGraph

DETECTOR_ID = "structural.cycle"


@dataclass(frozen=True)
class CycleDetection:
    cycles: tuple[tuple[str, ...], ...]
    budget_exceeded: bool
    expansions: int


def detect_cycles(cg: CurrencyGraph, cfg: dict[str, Any]) -> CycleDetection:
    min_len, max_len = int(cfg["min_length"]), int(cfg["max_length"])
    min_edge = int(cfg["min_edge_minor"])
    max_cycles, max_expansions = int(cfg["max_cycles"]), int(cfg["max_expansions"])
    g = cg.graph

    def ok(u: str, v: str) -> bool:
        return u != v and cg.edges[(u, v)].amount_minor >= min_edge

    found: list[tuple[str, ...]] = []
    expansions = 0
    exceeded = False

    def extend(path: list[str]) -> None:
        nonlocal expansions, exceeded
        for nxt in sorted(g.successors(path[-1])):
            if exceeded:
                return
            if not ok(path[-1], nxt):
                continue
            if nxt == path[0]:
                if len(path) >= min_len:
                    found.append(tuple(path))
                    if len(found) >= max_cycles:
                        exceeded = True
                continue
            if nxt < path[0] or nxt in path or len(path) >= max_len:
                continue
            expansions += 1
            if expansions > max_expansions:
                exceeded = True
                return
            extend([*path, nxt])

    for start in sorted(g.nodes):
        extend([start])
        if exceeded:
            break
    return CycleDetection(cycles=tuple(found), budget_exceeded=exceeded, expansions=expansions)
