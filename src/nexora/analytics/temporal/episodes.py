"""Repeated round-trip episodes around a structural cycle (spec §10.4, §9.4).

An *episode* is one transfer on every leg of the cycle, in cycle order, each strictly later
than the previous one (``strict``) or later-or-same-day (``possible``), within
``max_lag_days`` of it, and amount-consistent with it (``leg_amount_min_ratio`` ≤
next / previous ≤ ``leg_amount_max_ratio``). Episodes never share a transfer, so value is not
counted twice. Every rotation of the cycle is tried as the starting leg and the best is kept.

The result is expressed as a ``FlowResult`` so evidence, signals and policy treat it like any
other temporal claim: ``entry_minor`` is the volume on the starting leg, and the compatible
amounts are the starting-leg volume inside episodes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from nexora.analytics.temporal.flow import FlowResult, FlowStatus
from nexora.domain.transfers import ObservedTransfer, chronological_order, lag_days, lag_seconds

DETECTOR_ID = "temporal.episodes"
METHOD = "greedy_disjoint_episodes"


@dataclass(frozen=True)
class _Episodes:
    episodes: tuple[tuple[ObservedTransfer, ...], ...]
    ambiguous_links: int


def _key(t: ObservedTransfer) -> tuple[str, str, str]:
    return (t.observed_date.isoformat(), t.occurred_at.isoformat() if t.occurred_at else "", t.transaction_id)


def _find(
    legs: Sequence[Sequence[ObservedTransfer]],
    *,
    allow_ambiguous: bool,
    max_lag_days: int,
    lo: Fraction,
    hi: Fraction,
) -> _Episodes:
    used: set[str] = set()
    found: list[tuple[ObservedTransfer, ...]] = []
    ambiguous = 0
    for first in legs[0]:
        if first.transaction_id in used:
            continue
        chain = [first]
        amb = 0
        for leg in legs[1:]:
            prev = chain[-1]
            pick = None
            for y in leg:
                if y.transaction_id in used or y in chain:
                    continue
                order = chronological_order(prev, y)
                if order == "after" or (order == "ambiguous" and not allow_ambiguous):
                    continue
                if not 0 <= lag_days(prev, y) <= max_lag_days:
                    continue
                if not lo <= Fraction(y.amount_minor, prev.amount_minor) <= hi:
                    continue
                pick = y
                amb += order == "ambiguous"
                break
            if pick is None:
                break
            chain.append(pick)
        if len(chain) == len(legs):
            found.append(tuple(chain))
            used.update(t.transaction_id for t in chain)
            ambiguous += amb
    return _Episodes(tuple(found), ambiguous)


def cycle_episodes(
    legs: Sequence[Sequence[ObservedTransfer]],
    *,
    max_lag_days: int,
    leg_amount_min_ratio: str,
    leg_amount_max_ratio: str,
    min_episodes: int,
) -> FlowResult:
    ordered = [sorted((t for t in leg if t.eligible), key=_key) for leg in legs]
    all_tx = [t for leg in ordered for t in leg]
    precisions = {t.precision for t in all_tx}
    precision = "mixed" if len(precisions) > 1 else ("timestamp" if precisions == {"timestamp"} else "day")
    lo, hi = Fraction(leg_amount_min_ratio), Fraction(leg_amount_max_ratio)

    # One rotation for both modes keeps 0 <= strict <= possible <= entry on a common entry leg.
    candidates = []
    for r in range(len(ordered)):
        rotated = ordered[r:] + ordered[:r]
        s_eps = _find(rotated, allow_ambiguous=False, max_lag_days=max_lag_days, lo=lo, hi=hi)
        p_eps = _find(rotated, allow_ambiguous=True, max_lag_days=max_lag_days, lo=lo, hi=hi)
        if len(p_eps.episodes) < len(s_eps.episodes):
            p_eps = s_eps  # greedy matching with more options must never report less
        candidates.append((len(s_eps.episodes), len(p_eps.episodes), -r, s_eps, p_eps))
    n_strict, n_possible, neg_r, strict, possible = max(candidates, key=lambda c: c[:3])
    rotation = -neg_r
    if n_strict >= min_episodes:
        status: FlowStatus = "supported"
        chosen = strict
        limitations: list[str] = []
    elif n_possible >= min_episodes:
        status, chosen = "possible_ambiguous", possible
        limitations = ["same_day_order_unresolved" if precision != "timestamp" else "identical_timestamps"]
    else:
        status, chosen = "contradicted", possible
        limitations = ["no_repeated_round_trip" if possible.episodes else "chronology_rules_out_flow"]
    if precision != "timestamp":
        limitations.append("day_precision_no_intraday_order")
    limitations.append("intermediary_balances_unobserved")
    entry = sum(t.amount_minor for t in ordered[rotation]) if ordered else 0
    strict_minor = sum(e[0].amount_minor for e in strict.episodes)
    possible_minor = max(strict_minor, sum(e[0].amount_minor for e in possible.episodes))
    links = [(e[i], e[i + 1]) for e in chosen.episodes for i in range(len(e) - 1)]
    day_lags = [lag_days(x, y) for x, y in links]
    sec_lags = [s for s in (lag_seconds(x, y) for x, y in links) if s is not None]
    exact = precision == "timestamp" and bool(sec_lags) and len(sec_lags) == len(links)
    return FlowResult(
        status=status,
        entry_minor=entry,
        strict_compatible_minor=strict_minor,
        possible_compatible_minor=possible_minor,
        supporting_transaction_ids=tuple(sorted(t.transaction_id for e in chosen.episodes for t in e)),
        uncertain_transition_count=chosen.ambiguous_links,
        lag_days_min=min(day_lags) if day_lags else None,
        lag_days_max=max(day_lags) if day_lags else None,
        lag_seconds_min=min(sec_lags) if exact else None,
        lag_seconds_max=max(sec_lags) if exact else None,
        precision=precision,  # type: ignore[arg-type]
        limitations=tuple(limitations),
        method=METHOD,
    )
