"""Chronology- and capacity-constrained flow (spec §10).

Transfers are arranged in *layers* (e.g. feeder->centre then centre->downstream, or
one layer per hop of a path). Each transfer is a node-split vertex with capacity equal
to its amount, so no incoming value can be allocated twice. A transfer ``x`` in layer
``i`` links to ``y`` in layer ``i+1`` only when ``x.receiver == y.sender``, both share a
currency, ``y`` is not earlier than ``x`` and the calendar lag is within
``max_hop_lag_days``.

Two maximum flows are computed with exact integer capacities:

* ``strict`` — links where ``x`` is provably before ``y`` at the pair's precision;
* ``possible`` — additionally links whose order is ambiguous (same day for day-only
  records, identical instants for timestamps).

The value is an upper bound on chronology-compatible movement under the stated window.
It does not identify the source of funds: intermediary balances are unobserved.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

import networkx as nx

from nexora.domain.transfers import ObservedTransfer, chronological_order, lag_days, lag_seconds

DETECTOR_ID = "temporal.flow"
METHOD = "max_flow_exact"

FlowStatus = Literal["supported", "possible_ambiguous", "contradicted", "unavailable"]


@dataclass(frozen=True)
class FlowResult:
    status: FlowStatus
    entry_minor: int
    strict_compatible_minor: int
    possible_compatible_minor: int
    supporting_transaction_ids: tuple[str, ...]
    uncertain_transition_count: int
    lag_days_min: int | None
    lag_days_max: int | None
    lag_seconds_min: int | None
    lag_seconds_max: int | None
    precision: Literal["day", "timestamp", "mixed"]
    limitations: tuple[str, ...]
    method: str = METHOD
    eligible_transfers: int = 0
    processed_transfers: int = 0

    @property
    def chosen_compatible_minor(self) -> int:
        return self.strict_compatible_minor if self.status == "supported" else self.possible_compatible_minor

    @property
    def compatible_fraction_bp(self) -> int:
        if self.entry_minor <= 0:
            return 0
        return self.chosen_compatible_minor * 10_000 // self.entry_minor


def _sort_key(t: ObservedTransfer) -> tuple[str, str, str]:
    return (t.observed_date.isoformat(), t.occurred_at.isoformat() if t.occurred_at else "", t.transaction_id)


def _day_number(transfer: ObservedTransfer) -> int:
    return transfer.observed_date.toordinal()


def _unavailable(entry: int, precision: Literal["day", "timestamp", "mixed"], reason: str, eligible: int) -> FlowResult:
    return FlowResult(
        status="unavailable",
        entry_minor=entry,
        strict_compatible_minor=0,
        possible_compatible_minor=0,
        supporting_transaction_ids=(),
        uncertain_transition_count=0,
        lag_days_min=None,
        lag_days_max=None,
        lag_seconds_min=None,
        lag_seconds_max=None,
        precision=precision,
        limitations=(reason,),
        eligible_transfers=eligible,
    )


def layered_flow(
    layers: Sequence[Sequence[ObservedTransfer]],
    *,
    max_lag_days: int,
    min_compatible_fraction: Fraction | str | float,
    max_transfers: int,
) -> FlowResult:
    ordered = [sorted({t.transaction_id: t for t in layer if t.eligible}.values(), key=_sort_key) for layer in layers]
    all_tx = [t for layer in ordered for t in layer]
    precisions = {t.precision for t in all_tx}
    precision: Literal["day", "timestamp", "mixed"] = (
        "mixed" if len(precisions) > 1 else ("timestamp" if precisions == {"timestamp"} else "day")
    )
    entry = sum(t.amount_minor for t in ordered[0]) if ordered else 0
    if len(ordered) < 2 or any(not layer for layer in ordered):
        return _unavailable(entry, precision, "missing_leg", len(all_tx))
    if len({t.currency for t in all_tx}) > 1:
        return _unavailable(entry, precision, "currency_mix", len(all_tx))
    if len(all_tx) > max_transfers:
        return _unavailable(entry, precision, "flow_budget_exceeded", len(all_tx))
    seen: set[str] = set()
    for t in all_tx:
        if t.transaction_id in seen:
            # A transfer may not occupy two layers: that would double its capacity.
            return _unavailable(entry, precision, "transfer_reused_across_layers", len(all_tx))
        seen.add(t.transaction_id)

    links: list[tuple[int, ObservedTransfer, ObservedTransfer, bool]] = []
    for i in range(len(ordered) - 1):
        by_sender: dict[str, list[ObservedTransfer]] = defaultdict(list)
        for transfer in ordered[i + 1]:
            by_sender[transfer.sender].append(transfer)
        for x in ordered[i]:
            candidates = by_sender.get(x.receiver, ())
            start = bisect_left(candidates, x.observed_date.toordinal(), key=_day_number)
            end = bisect_right(candidates, x.observed_date.toordinal() + max_lag_days, key=_day_number)
            for y in candidates[start:end]:
                order = chronological_order(x, y)
                if order == "after":
                    continue
                links.append((i, x, y, order == "ambiguous"))

    def solve(
        include_ambiguous: bool,
    ) -> tuple[int, dict[str, int], list[tuple[ObservedTransfer, ObservedTransfer, bool]]]:
        g: nx.DiGraph = nx.DiGraph()
        g.add_node("S")
        g.add_node("T")
        last = len(ordered) - 1
        for i, layer in enumerate(ordered):
            for t in layer:
                vin, vout = ("in", i, t.transaction_id), ("out", i, t.transaction_id)
                g.add_edge(vin, vout, capacity=t.amount_minor)
                if i == 0:
                    g.add_edge("S", vin)  # unbounded; the split edge carries the cap
                if i == last:
                    g.add_edge(vout, "T")
        for i, x, y, ambiguous in links:
            if ambiguous and not include_ambiguous:
                continue
            g.add_edge(("out", i, x.transaction_id), ("in", i + 1, y.transaction_id))
        value, flow = nx.maximum_flow(g, "S", "T")
        used: dict[str, int] = {}
        for i, layer in enumerate(ordered):
            for t in layer:
                f = flow[("in", i, t.transaction_id)][("out", i, t.transaction_id)]
                if f > 0:
                    used[t.transaction_id] = int(f)
        used_links = [
            (x, y, amb)
            for i, x, y, amb in links
            if (include_ambiguous or not amb)
            and flow.get(("out", i, x.transaction_id), {}).get(("in", i + 1, y.transaction_id), 0) > 0
        ]
        return int(value), used, used_links

    strict_value, strict_used, strict_links = solve(include_ambiguous=False)
    possible_value, possible_used, possible_links = solve(include_ambiguous=True)

    fraction = Fraction(str(min_compatible_fraction))
    meets = lambda v: entry > 0 and Fraction(v, entry) >= fraction  # noqa: E731
    limitations: list[str] = []
    if meets(strict_value):
        status: FlowStatus = "supported"
        used, used_links = strict_used, strict_links
    elif meets(possible_value):
        status = "possible_ambiguous"
        used, used_links = possible_used, possible_links
        limitations.append("same_day_order_unresolved" if precision != "timestamp" else "identical_timestamps")
    else:
        status = "contradicted"
        used, used_links = possible_used, possible_links
        limitations.append("chronology_rules_out_flow" if possible_value == 0 else "insufficient_compatible_amount")
    if precision != "timestamp":
        limitations.append("day_precision_no_intraday_order")
    limitations.append("intermediary_balances_unobserved")

    day_lags = [lag_days(x, y) for x, y, _ in used_links]
    sec_lags = [s for s in (lag_seconds(x, y) for x, y, _ in used_links) if s is not None]
    exact_seconds = precision == "timestamp" and len(sec_lags) == len(used_links) and bool(sec_lags)
    return FlowResult(
        status=status,
        entry_minor=entry,
        strict_compatible_minor=strict_value,
        possible_compatible_minor=possible_value,
        supporting_transaction_ids=tuple(sorted(used)),
        uncertain_transition_count=sum(1 for _, _, amb in used_links if amb),
        lag_days_min=min(day_lags) if day_lags else None,
        lag_days_max=max(day_lags) if day_lags else None,
        lag_seconds_min=min(sec_lags) if exact_seconds else None,
        lag_seconds_max=max(sec_lags) if exact_seconds else None,
        precision=precision,
        limitations=tuple(limitations),
        eligible_transfers=len(all_tx),
        processed_transfers=len(all_tx),
    )
