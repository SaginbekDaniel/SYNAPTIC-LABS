from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from nexora.domain.transfers import ObservedTransfer

BASE = date(2026, 7, 1)


def tx(
    tid: str,
    sender: str,
    receiver: str,
    amount: int,
    day: int = 0,
    *,
    seconds: int | None = None,
    currency: str = "KZT",
    status: str = "posted",
) -> ObservedTransfer:
    d = BASE + timedelta(days=day)
    occurred = None if seconds is None else datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(seconds=seconds)
    return ObservedTransfer(
        transaction_id=tid,
        source_transaction_id=tid,
        sender=sender,
        receiver=receiver,
        amount_minor=amount,
        currency=currency,
        observed_date=d,
        occurred_at=occurred,
        precision="timestamp" if occurred else "day",
        status=status,  # type: ignore[arg-type]
    )
