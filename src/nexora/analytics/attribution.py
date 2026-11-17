"""Fungibility-aware (pro-rata) attribution bounds for pass-through hypotheses.

Money inside an account is fungible. When a pass-through account also receives other funds —
or spends from an opening balance the data does not show — only part of its outflow can be
attributed to the formation's entry funds. Without balance data the defensible convention is
*pro rata* ("haircut") attribution over the account's observed funding.

The observed funding of an account is ``max(incoming, outgoing)``: when an account pays out
more than it received in the window, the difference must have come from an unobserved opening
balance, which is treated as funds of unknown origin rather than ignored.

All arithmetic is exact integer floor division on minor units.
"""

from __future__ import annotations

from collections.abc import Sequence

from nexora.analytics.graph_builder import CurrencyGraph


def funding(cg: CurrencyGraph, account: str) -> int:
    m = cg.metrics[account]
    return max(m.incoming_minor, m.outgoing_minor)


def consolidation_pro_rata(cg: CurrencyGraph, centre: str, entry_minor: int) -> int:
    """Share of the centre's outflow attributable to ``entry_minor`` of its funding."""
    f = funding(cg, centre)
    if f <= 0:
        return 0
    return min(entry_minor, cg.metrics[centre].outgoing_minor * entry_minor // f)


def path_pro_rata(cg: CurrencyGraph, path: Sequence[str]) -> int:
    """Entry funds that can be traced to the end of ``path`` under pro-rata attribution.

    At each intermediary the traced amount continuing to the next hop is
    ``edge(b, next) * traced_in / funding(b)``.
    """
    traced = cg.edges[(path[0], path[1])].amount_minor
    for i in range(1, len(path) - 1):
        f = funding(cg, path[i])
        if f <= 0:
            return 0
        traced = min(traced, cg.edges[(path[i], path[i + 1])].amount_minor * traced // f)
    return traced


def distribution_pro_rata(cg: CurrencyGraph, source: str, recipients: Sequence[str]) -> int:
    """Dispersed funds attributable to the recipients' onward outflow (excluding returns to source)."""
    total = 0
    for r in recipients:
        f = funding(cg, r)
        if f <= 0:
            continue
        received = cg.edges[(source, r)].amount_minor
        onward = cg.metrics[r].outgoing_minor - (cg.edges[(r, source)].amount_minor if (r, source) in cg.edges else 0)
        total += min(received, max(0, onward) * received // f)
    return total
