"""Money semantics (ADR-003).

Amounts are always integer minor units (tiyn for KZT). Floats are rejected at every
boundary because IEEE-754 cannot represent most decimal amounts exactly. JSON transport
uses decimal strings so values beyond 2^53-1 survive JavaScript clients.
"""

from __future__ import annotations

import re

# Matches the database column type NUMERIC(38,0).
MAX_AMOUNT_MINOR = 10**38 - 1
_DIGITS = re.compile(r"^[0-9]+$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class MoneyError(ValueError):
    """Raised when an amount or currency cannot be represented exactly."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_amount_minor(value: object) -> int:
    """Parse a strictly positive integer amount in minor units.

    Accepts ``int`` or a string of ASCII digits. Rejects floats, signs, decimal points,
    exponents, whitespace-only strings and booleans.
    """
    if isinstance(value, bool):
        raise MoneyError("AMOUNT_INVALID", "boolean is not an amount")
    if isinstance(value, float):
        raise MoneyError("AMOUNT_FLOAT_REJECTED", "floating-point amounts are not accepted; use integer minor units")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str):
        text = value.strip()
        if not _DIGITS.match(text):
            raise MoneyError("AMOUNT_INVALID", "amount_minor must be a string of digits (integer minor units)")
        amount = int(text)
    else:
        raise MoneyError("AMOUNT_INVALID", f"unsupported amount type {type(value).__name__}")
    if amount <= 0:
        raise MoneyError("AMOUNT_NOT_POSITIVE", "amount_minor must be greater than zero")
    if amount > MAX_AMOUNT_MINOR:
        raise MoneyError("AMOUNT_OUT_OF_RANGE", "amount_minor exceeds NUMERIC(38,0)")
    return amount


def parse_currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY.match(value.strip()):
        raise MoneyError("CURRENCY_INVALID", "currency must be a three-letter upper-case ISO 4217 code")
    return value.strip()


def amount_to_str(amount_minor: int) -> str:
    """Canonical JSON representation of an amount (decimal string)."""
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise MoneyError("AMOUNT_INVALID", "amount must be int")
    return str(amount_minor)
