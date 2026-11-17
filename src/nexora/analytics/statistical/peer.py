"""Peer-relative turnover concentration (spec §10.1), signal family PEER_STATISTICS.

Question answered: *is this account's turnover unusually concentrated in time compared
with accounts of similar activity in the same snapshot?* Consolidation and
distribution accounts used for laundering typically move most of their money in a few
days; settlement processors, suppliers and treasury accounts turn money over steadily.

* **Statistic** — burst share: the largest share of an account's observed turnover
  (incoming + outgoing, one currency, posted, no self-transfers) that falls inside any
  ``window_days`` consecutive calendar days. Exact integers; reported in basis points.
* **Cohort** — other accounts of the same currency graph whose transaction count lies
  within a factor ``F`` of the subject's. ``F`` widens through ``cohort_count_factors``
  until ``min_cohort`` peers qualify; then, if ``fallback_all_active``, every other active
  account (reported as ``peer_cohort_all_active_accounts``); otherwise the signal is
  ``unavailable``. Comparing
  with a single global threshold would punish every low-activity account, because the
  burst share of an account with few transfers is high by construction.
* **Fence** — Tukey outlier fence ``Q3 + k·IQR`` of the cohort (``k = 1.5``). Median/MAD
  z-scores collapse on small, discrete cohorts, and the "far-out" ``k = 3`` fence lies
  above the bounded 0-100 % range for low-count cohorts, so it could never fire.

Outcomes: ``supported`` (above the fence and above ``min_burst_share``), ``contradicted``
(no more concentrated than the cohort median — a typical, steady turnover profile),
``possible_ambiguous`` (in between), ``unavailable`` (no adequate cohort).

The burst share is time-based, like the temporal flow engine, but answers a different
question (account-level concentration vs. ordering and capacity of specific funds). The
two are not independent; the risk policy weights the family accordingly (spec §10.3).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Any, Literal

from nexora.analytics.graph_builder import CurrencyGraph
from nexora.domain.transfers import ObservedTransfer

DETECTOR_ID = "statistical.peer_concentration"
PeerStatus = Literal["supported", "possible_ambiguous", "contradicted", "unavailable"]


@dataclass(frozen=True)
class AccountProfile:
    account_id: str
    transfer_count: int
    turnover_minor: int
    burst_minor: int
    burst_start: date | None
    burst_transaction_ids: tuple[str, ...]

    @property
    def burst_bp(self) -> int:
        return 0 if self.turnover_minor == 0 else self.burst_minor * 10_000 // self.turnover_minor


@dataclass(frozen=True)
class PeerResult:
    status: PeerStatus
    subject: AccountProfile
    window_days: int
    cohort_size: int
    cohort_factor: int | None
    cohort_q1_bp: int | None
    cohort_median_bp: int | None
    cohort_q3_bp: int | None
    fence_bp: int | None
    strength: float | None
    limitations: tuple[str, ...]


def _profile(account: str, transfers: list[ObservedTransfer], window_days: int) -> AccountProfile:
    by_day: dict[date, int] = defaultdict(int)
    for t in transfers:
        by_day[t.observed_date] += t.amount_minor
    days = sorted(by_day)
    turnover = sum(by_day.values())
    best = 0
    best_start: date | None = None
    for start in days:  # windows anchored on active days cover every maximal window
        end = start + timedelta(days=window_days - 1)
        vol = sum(v for d, v in by_day.items() if start <= d <= end)
        if vol > best:
            best, best_start = vol, start
    ids: tuple[str, ...] = ()
    if best_start is not None:
        end = best_start + timedelta(days=window_days - 1)
        ids = tuple(sorted(t.transaction_id for t in transfers if best_start <= t.observed_date <= end))
    return AccountProfile(account, len(transfers), turnover, best, best_start, ids)


class PeerIndex:
    """Burst profiles of every account in one currency graph (computed once per snapshot)."""

    def __init__(self, cg: CurrencyGraph, transfers: dict[str, ObservedTransfer], window_days: int):
        self.window_days = window_days
        per_account: dict[str, list[ObservedTransfer]] = defaultdict(list)
        for edge in cg.edges.values():
            for tid in edge.transaction_ids:
                t = transfers[tid]
                per_account[t.sender].append(t)
                per_account[t.receiver].append(t)
        self.profiles = {a: _profile(a, txs, window_days) for a, txs in sorted(per_account.items())}

    def assess(self, subject: str, cfg: dict[str, Any]) -> PeerResult:
        prof = self.profiles.get(subject) or AccountProfile(subject, 0, 0, 0, None, ())
        min_cohort = int(cfg["min_cohort"])
        fence_k = Fraction(str(cfg["fence_iqr_multiplier"]))
        min_burst_bp = int(Fraction(str(cfg["min_burst_share"])) * 10_000)
        cohort: list[int] = []
        factor_used: int | None = None
        for factor in (int(f) for f in cfg["cohort_count_factors"]):
            lo, hi = Fraction(prof.transfer_count, factor), prof.transfer_count * factor
            cohort = [
                p.burst_bp
                for a, p in self.profiles.items()
                if a != subject and p.transfer_count >= 2 and lo <= p.transfer_count <= hi
            ]
            if len(cohort) >= min_cohort:
                factor_used = factor
                break
        if factor_used is None and cfg.get("fallback_all_active", False):
            # Last resort for hubs in small snapshots: every other active account. Conservative in
            # both directions: low-activity accounts are bursty by construction, so the fence is
            # high (few "supported"), and a hub at or below their median is clearly not concentrated.
            cohort = [p.burst_bp for a, p in self.profiles.items() if a != subject and p.transfer_count >= 2]
            if len(cohort) >= min_cohort:
                factor_used = 0
        if factor_used is None or prof.turnover_minor == 0:
            return PeerResult(
                "unavailable", prof, self.window_days, len(cohort), None, None, None, None, None, None,
                ("peer_cohort_too_small",),
            )  # fmt: skip
        q1, median, q3 = (round(q) for q in statistics.quantiles(cohort, n=4, method="inclusive"))
        fence = q3 + int(fence_k * (q3 - q1))
        burst = prof.burst_bp
        status: PeerStatus
        strength: float | None
        if burst > fence and burst >= min_burst_bp:
            status = "supported"
            headroom = max(1, 10_000 - fence)
            strength = round(0.6 + 0.4 * min(1.0, (burst - fence) / headroom), 4)
        elif burst <= median:
            status, strength = "contradicted", 0.0
        else:
            status, strength = "possible_ambiguous", 0.0
        limitations = ["peer_cohort_same_snapshot", "no_business_category_data"]
        if factor_used == 0:
            limitations.append("peer_cohort_all_active_accounts")
        elif factor_used != int(cfg["cohort_count_factors"][0]):
            limitations.append("peer_cohort_widened")
        return PeerResult(
            status, prof, self.window_days, len(cohort), factor_used, q1, median, q3, fence, strength,
            tuple(limitations),
        )  # fmt: skip
