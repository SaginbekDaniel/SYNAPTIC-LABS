"""Benign behavioural context: observed counter-evidence for hub-shaped formations.

Spec §11.4: "an ordinary payment processor shared by many merchants should remain explainable
as a possibly benign hub". Funnel and fan-out structures are shared by fraud and by ordinary
operating accounts (processors, employers, lenders, billers). This module computes *observed*
facts that the operating-account explanation predicts and the episodic mule explanation does
not. Each indicator is published as a ``counterevidence`` object with its transactions, so an
analyst can verify it; none of them is a verdict.

Indicators (all computed for every formation, never per account id):

* ``CTX_RECURRING_RELATIONSHIPS`` — most of the formation's counterparty volume comes from
  relationships active on dates at least ``recurrence_min_span_days`` apart. Episodic
  collection or dispersal happens in one burst.
* ``CTX_SCHEDULED_PAYOUTS`` — most of the subject's outflow goes to recipients paid on at least
  ``scheduled_min_payout_dates`` distinct dates (a settlement or payroll schedule).
* ``CTX_RECIPROCAL_RELATIONSHIPS`` — most counterparties also had money flow in the opposite
  direction with the subject (loans and repayments, refunds, shared expenses).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from nexora.analytics.graph_builder import CurrencyGraph
from nexora.domain.transfers import ObservedTransfer


@dataclass(frozen=True)
class ContextIndicator:
    code: str
    observations: dict[str, Any]
    thresholds: dict[str, Any]
    transaction_ids: tuple[str, ...]


def _dates(cg: CurrencyGraph, transfers: dict[str, ObservedTransfer], pair: tuple[str, str]) -> list[Any]:
    edge = cg.edges.get(pair)
    return sorted({transfers[t].observed_date for t in edge.transaction_ids}) if edge else []


def hub_context(
    cg: CurrencyGraph,
    transfers: dict[str, ObservedTransfer],
    *,
    subject: str,
    counterparties: Sequence[str],
    direction: str,
    cfg: dict[str, Any],
) -> list[ContextIndicator]:
    """``direction`` is ``"in"`` when counterparties pay the subject (funnel), else ``"out"``."""
    span = int(cfg["recurrence_min_span_days"])
    min_share = Fraction(str(cfg["min_share"]))
    min_payout_dates = int(cfg["scheduled_min_payout_dates"])
    out: list[ContextIndicator] = []

    def pair(c: str) -> tuple[str, str]:
        return (c, subject) if direction == "in" else (subject, c)

    def reverse(c: str) -> tuple[str, str]:
        return (subject, c) if direction == "in" else (c, subject)

    volume = {c: cg.edges[pair(c)].amount_minor for c in counterparties}
    total = sum(volume.values())
    recurring = [c for c in counterparties if (d := _dates(cg, transfers, pair(c))) and (d[-1] - d[0]).days >= span]
    recurring_volume = sum(volume[c] for c in recurring)
    if total > 0 and Fraction(recurring_volume, total) >= min_share:
        out.append(
            ContextIndicator(
                "CTX_RECURRING_RELATIONSHIPS",
                {
                    "recurring_counterparties": len(recurring),
                    "counterparties": len(counterparties),
                    "recurring_share_bp": recurring_volume * 10_000 // total,
                },
                {"recurrence_min_span_days": span, "min_share": str(min_share)},
                tuple(sorted(t for c in recurring for t in cg.edges[pair(c)].transaction_ids)),
            )
        )

    outflow_total = cg.metrics[subject].outgoing_minor
    if outflow_total > 0:
        scheduled = [
            r
            for r in sorted(cg.graph.successors(subject))
            if r != subject and len(_dates(cg, transfers, (subject, r))) >= min_payout_dates
        ]
        scheduled_volume = sum(cg.edges[(subject, r)].amount_minor for r in scheduled)
        if Fraction(scheduled_volume, outflow_total) >= min_share:
            out.append(
                ContextIndicator(
                    "CTX_SCHEDULED_PAYOUTS",
                    {
                        "scheduled_recipients": len(scheduled),
                        "max_payout_dates": max(len(_dates(cg, transfers, (subject, r))) for r in scheduled),
                        "scheduled_share_bp": scheduled_volume * 10_000 // outflow_total,
                    },
                    {"scheduled_min_payout_dates": min_payout_dates, "min_share": str(min_share)},
                    tuple(sorted(t for r in scheduled for t in cg.edges[(subject, r)].transaction_ids)),
                )
            )

    reciprocal = [c for c in counterparties if reverse(c) in cg.edges]
    if counterparties and Fraction(len(reciprocal), len(counterparties)) >= min_share:
        out.append(
            ContextIndicator(
                "CTX_RECIPROCAL_RELATIONSHIPS",
                {"reciprocal_counterparties": len(reciprocal), "counterparties": len(counterparties)},
                {"min_share": str(min_share)},
                tuple(sorted(t for c in reciprocal for t in cg.edges[reverse(c)].transaction_ids)),
            )
        )
    return out
