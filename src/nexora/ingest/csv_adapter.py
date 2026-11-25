"""Streaming CSV adapter with schema mapping and fatal-vs-row error tiers."""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter
from collections.abc import Mapping

REQUIRED_COLUMNS = ("sender_account_id", "receiver_account_id", "amount_minor", "currency")
OPTIONAL_COLUMNS = ("source_transaction_id", "observed_date", "occurred_at", "status")
DEFAULT_MAX_ROWS = 200_000


class CsvSchemaError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_csv_rows(
    content: bytes, *, max_rows: int = DEFAULT_MAX_ROWS
) -> tuple[list[tuple[int, Mapping[str, object]]], str]:
    """Return ``(rows, content_sha256)``. Row numbers are 1-based data rows (header excluded).

    If the file has no ``source_transaction_id`` column, a stable id is derived from the
    canonical tuple plus its occurrence index among identical tuples, so re-importing the
    same file is idempotent while two genuinely distinct equal-looking transfers are both
    kept (spec §7.1).
    """
    digest = hashlib.sha256(content).hexdigest()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvSchemaError("CSV_ENCODING_INVALID", "file must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [name.strip().casefold() for name in (reader.fieldnames or [])]
    if len(header) != len(set(header)):
        raise CsvSchemaError("CSV_SCHEMA_INVALID", "duplicate normalized column header")
    reader.fieldnames = header
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise CsvSchemaError("CSV_SCHEMA_INVALID", f"missing required columns: {', '.join(missing)}")
    if "observed_date" not in header and "occurred_at" not in header:
        raise CsvSchemaError("CSV_SCHEMA_INVALID", "one of observed_date or occurred_at columns is required")
    derive_ids = "source_transaction_id" not in header
    occurrences: Counter[str] = Counter()
    rows: list[tuple[int, Mapping[str, object]]] = []
    for index, raw in enumerate(reader, start=1):
        if index > max_rows:
            raise CsvSchemaError("CSV_TOO_MANY_ROWS", f"file exceeds {max_rows} rows")
        row: dict[str, object] = {column: value for column, value in raw.items() if column is not None}
        if derive_ids:
            tuple_key = "|".join(
                str(row.get(c) or "").strip() for c in (*REQUIRED_COLUMNS, "observed_date", "occurred_at")
            )
            occurrences[tuple_key] += 1
            base = hashlib.sha256(tuple_key.encode()).hexdigest()[:24]
            row["source_transaction_id"] = f"derived-{base}-{occurrences[tuple_key]}"
        rows.append((index, row))
    return rows, digest
