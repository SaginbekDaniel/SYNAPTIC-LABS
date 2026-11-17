"""Deterministic identifiers (DATA-003).

Analysis outputs derive their IDs from canonical content so that the same input in any
row order yields identical snapshot/formation/evidence IDs, and so that publishing is
idempotent (at-least-once jobs + idempotent effects).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

NEXORA_NAMESPACE = uuid.UUID("6f1c3a52-5b0e-4f7e-9a51-2a8c0d4e7b11")


def stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(NEXORA_NAMESPACE, "\x1f".join(parts)))


def canonical_json(value: Any) -> str:
    """Stable serialization: sorted keys, no whitespace, NaN/Infinity rejected."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def transaction_uuid(dataset_id: str, source_id: str, source_transaction_id: str) -> str:
    return stable_uuid("tx", dataset_id, source_id, source_transaction_id)
