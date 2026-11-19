"""Row-level validation into canonical records (spec §7.2).

Tiers: *fatal* errors abort a file (raised by adapters); *row quarantine* issues are
returned per row; *warnings* (e.g. day-only precision) are counted in the report.
Raw payloads are never echoed back in reports — only row numbers, fields and codes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from nexora.domain.ids import canonical_json, sha256_hex
from nexora.domain.money import MoneyError, amount_to_str, parse_amount_minor, parse_currency
from nexora.domain.transfers import TimePrecision

MAX_ID_LENGTH = 128
VALID_STATUSES = ("posted", "reversed", "cancelled")


@dataclass(frozen=True, slots=True)
class CanonicalRecord:
    source_id: str
    source_transaction_id: str
    sender_account_id: str
    receiver_account_id: str
    amount_minor: int
    currency: str
    observed_date: date
    occurred_at: datetime | None
    time_precision: TimePrecision
    status: str
    is_synthetic: bool

    def content_hash(self) -> str:
        """Hash of the canonical, ingestion-independent content (``raw_record_hash``)."""
        return sha256_hex(
            canonical_json(
                {
                    "source_id": self.source_id,
                    "source_transaction_id": self.source_transaction_id,
                    "sender": self.sender_account_id,
                    "receiver": self.receiver_account_id,
                    "amount_minor": amount_to_str(self.amount_minor),
                    "currency": self.currency,
                    "observed_date": self.observed_date.isoformat(),
                    "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
                    "time_precision": self.time_precision,
                    "status": self.status,
                }
            )
        )


@dataclass(frozen=True, slots=True)
class RowIssue:
    row_number: int
    code: str
    field: str | None
    message: str


@dataclass
class ImportReport:
    processed: int = 0
    accepted: int = 0
    duplicated_identical: int = 0
    quarantined: int = 0
    rejected: int = 0
    warning_count: int = 0
    error_codes: Counter[str] = field(default_factory=Counter)
    warning_codes: Counter[str] = field(default_factory=Counter)
    examples: list[RowIssue] = field(default_factory=list)
    content_sha256: str | None = None

    MAX_EXAMPLES = 20

    def quarantine(self, issue: RowIssue) -> None:
        self.quarantined += 1
        self.error_codes[issue.code] += 1
        if len(self.examples) < self.MAX_EXAMPLES:
            self.examples.append(issue)

    def warn(self, code: str, count: int = 1) -> None:
        self.warning_count += count
        self.warning_codes[code] += count

    def as_dict(self) -> dict[str, object]:
        return {
            "processed": self.processed,
            "accepted": self.accepted,
            "duplicated_identical": self.duplicated_identical,
            "quarantined": self.quarantined,
            "rejected": self.rejected,
            "warning_count": self.warning_count,
            "error_codes": dict(sorted(self.error_codes.items())),
            "warning_codes": dict(sorted(self.warning_codes.items())),
            "examples": [
                {"row_number": e.row_number, "code": e.code, "field": e.field, "message": e.message}
                for e in self.examples
            ],
            "content_sha256": self.content_sha256,
        }


def _clean_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        # IDs are opaque strings; a numeric type here means an upstream lossy conversion.
        return None
    text = value.strip()
    if not text or len(text) > MAX_ID_LENGTH or not text.isprintable():
        return None
    return text


def _parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("naive")
    return parsed.astimezone(UTC)


def parse_record(
    raw: Mapping[str, object], *, row_number: int, source_id: str, is_synthetic: bool
) -> CanonicalRecord | RowIssue:
    def issue(code: str, field_name: str | None, message: str) -> RowIssue:
        return RowIssue(row_number=row_number, code=code, field=field_name, message=message)

    tx_id = _clean_id(raw.get("source_transaction_id"))
    if tx_id is None:
        return issue("MISSING_TRANSACTION_ID", "source_transaction_id", "missing or invalid transaction id")
    sender = _clean_id(raw.get("sender_account_id"))
    if sender is None:
        return issue("MISSING_ACCOUNT_ID", "sender_account_id", "missing or invalid sender account id")
    receiver = _clean_id(raw.get("receiver_account_id"))
    if receiver is None:
        return issue("MISSING_ACCOUNT_ID", "receiver_account_id", "missing or invalid receiver account id")

    try:
        amount = parse_amount_minor(raw.get("amount_minor"))
    except MoneyError as exc:
        return issue(exc.code, "amount_minor", str(exc))
    try:
        currency = parse_currency(raw.get("currency"))
    except MoneyError as exc:
        return issue(exc.code, "currency", str(exc))

    occurred_raw = raw.get("occurred_at")
    occurred_at: datetime | None = None
    if isinstance(occurred_raw, str) and occurred_raw.strip():
        try:
            occurred_at = _parse_timestamp(occurred_raw)
        except ValueError:
            return issue("TIMESTAMP_INVALID", "occurred_at", "occurred_at must be ISO-8601 with an explicit offset")

    date_raw = raw.get("observed_date")
    observed: date | None = None
    if isinstance(date_raw, str) and date_raw.strip():
        try:
            observed = date.fromisoformat(date_raw.strip())
        except ValueError:
            return issue("DATE_INVALID", "observed_date", "observed_date must be YYYY-MM-DD")
    if observed is not None and occurred_at is not None and abs((occurred_at.date() - observed).days) > 1:
        # The posting date may differ from the UTC date of the timestamp by one day (time zones),
        # never more: ordering uses the timestamp while lags use the date, so a wider gap would let
        # the two disagree about chronology.
        return issue(
            "DATE_TIMESTAMP_MISMATCH", "observed_date", "observed_date contradicts occurred_at by more than one day"
        )
    if observed is None:
        if occurred_at is None:
            return issue("DATE_MISSING", "observed_date", "either observed_date or occurred_at is required")
        observed = occurred_at.date()

    status_raw = raw.get("status")
    status = status_raw.strip() if isinstance(status_raw, str) and status_raw.strip() else "posted"
    if status not in VALID_STATUSES:
        return issue("STATUS_UNSUPPORTED", "status", f"status must be one of {', '.join(VALID_STATUSES)}")

    return CanonicalRecord(
        source_id=source_id,
        source_transaction_id=tx_id,
        sender_account_id=sender,
        receiver_account_id=receiver,
        amount_minor=amount,
        currency=currency,
        observed_date=observed,
        occurred_at=occurred_at,
        time_precision="timestamp" if occurred_at is not None else "day",
        status=status,
        is_synthetic=is_synthetic,
    )


def prepare_batch(
    rows: Sequence[tuple[int, Mapping[str, object]]], *, source_id: str, is_synthetic: bool
) -> tuple[list[CanonicalRecord], ImportReport]:
    """Validate rows and deduplicate *within* the batch.

    Identical repeats of the same ``(source_id, source_transaction_id)`` are counted as
    ``duplicated_identical``; a repeat with different content is quarantined as
    ``CONFLICTING_TRANSACTION_DUPLICATE`` (the first occurrence is kept).
    """
    report = ImportReport()
    accepted: dict[str, CanonicalRecord] = {}
    for row_number, raw in rows:
        report.processed += 1
        parsed = parse_record(raw, row_number=row_number, source_id=source_id, is_synthetic=is_synthetic)
        if isinstance(parsed, RowIssue):
            report.quarantine(parsed)
            continue
        existing = accepted.get(parsed.source_transaction_id)
        if existing is not None:
            if existing.content_hash() == parsed.content_hash():
                report.duplicated_identical += 1
            else:
                report.quarantine(
                    RowIssue(
                        row_number,
                        "CONFLICTING_TRANSACTION_DUPLICATE",
                        "source_transaction_id",
                        "transaction id repeated with different content",
                    )
                )
            continue
        accepted[parsed.source_transaction_id] = parsed
        if parsed.time_precision == "day":
            report.warn("DAY_PRECISION_ONLY")
        if parsed.sender_account_id == parsed.receiver_account_id:
            report.warn("SELF_TRANSFER")
    records = list(accepted.values())
    report.accepted = len(records)
    return records, report
