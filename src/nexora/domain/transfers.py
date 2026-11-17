"""Observed transfers and precision-aware chronology (ADR-006).

A day-precision record never carries an intraday timestamp. Ordering between two
records is computed at the coarsest precision of the pair; equal days (or equal
instants) are *ambiguous*, never silently ordered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

TimePrecision = Literal["day", "timestamp"]
TransferStatus = Literal["posted", "reversed", "cancelled"]
Order = Literal["before", "ambiguous", "after"]

#: Reversal policy v1: only ``posted`` records contribute to graph aggregates and flows.
ELIGIBLE_STATUSES: frozenset[str] = frozenset({"posted"})


@dataclass(frozen=True, slots=True)
class ObservedTransfer:
    transaction_id: str  # canonical NEXORA id (deterministic per dataset/source/source id)
    source_transaction_id: str
    sender: str
    receiver: str
    amount_minor: int
    currency: str
    observed_date: date
    occurred_at: datetime | None
    precision: TimePrecision
    status: TransferStatus = "posted"

    def __post_init__(self) -> None:
        if self.precision == "day" and self.occurred_at is not None:
            raise ValueError("day-precision transfer must not carry a timestamp")
        if self.precision == "timestamp":
            if self.occurred_at is None:
                raise ValueError("timestamp-precision transfer requires occurred_at")
            if self.occurred_at.tzinfo is None:
                raise ValueError("occurred_at must be timezone-aware")
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int) or self.amount_minor <= 0:
            raise ValueError("amount_minor must be a positive int")

    @property
    def eligible(self) -> bool:
        return self.status in ELIGIBLE_STATUSES

    @property
    def is_self_transfer(self) -> bool:
        return self.sender == self.receiver


def chronological_order(a: ObservedTransfer, b: ObservedTransfer) -> Order:
    """Order of ``a`` relative to ``b`` at the coarsest defensible precision."""
    if a.precision == "timestamp" and b.precision == "timestamp":
        assert a.occurred_at is not None and b.occurred_at is not None
        if a.occurred_at < b.occurred_at:
            return "before"
        if a.occurred_at > b.occurred_at:
            return "after"
        return "ambiguous"
    if a.observed_date < b.observed_date:
        return "before"
    if a.observed_date > b.observed_date:
        return "after"
    return "ambiguous"


def lag_days(a: ObservedTransfer, b: ObservedTransfer) -> int:
    """Calendar-day difference ``b - a``. Valid for any precision."""
    return (b.observed_date - a.observed_date).days


def lag_seconds(a: ObservedTransfer, b: ObservedTransfer) -> int | None:
    """Exact elapsed seconds, or ``None`` when either record lacks a source timestamp."""
    if a.occurred_at is None or b.occurred_at is None:
        return None
    return int((b.occurred_at - a.occurred_at).total_seconds())
