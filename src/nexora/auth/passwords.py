"""Password hashing with Argon2id (argon2-cffi, RFC 9106 low-memory profile: t=3, m=64 MiB, p=4)."""

from __future__ import annotations

import threading
import unicodedata
from functools import lru_cache

from argon2 import PasswordHasher, profiles
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256

_hasher = PasswordHasher.from_parameters(profiles.RFC_9106_LOW_MEMORY)
# Each verification allocates 64 MiB. Bound concurrent hashing so a burst of sign-in requests
# cannot exhaust the API container's memory (512 MiB on Railway); excess requests queue briefly.
_slots = threading.BoundedSemaphore(2)


def normalize_password(password: str) -> str:
    # NFKC so the same password typed on different keyboards/platforms verifies identically.
    return unicodedata.normalize("NFKC", password)


def password_problem(password: str) -> str | None:
    """Why a new password is unacceptable, or None. Length is what matters (NIST SP 800-63B)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"password must be at most {MAX_PASSWORD_LENGTH} characters"
    return None


def hash_password(password: str) -> str:
    with _slots:
        return _hasher.hash(normalize_password(password))


def verify_password(stored_hash: str, password: str) -> bool:
    with _slots:
        try:
            return _hasher.verify(stored_hash, normalize_password(password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def is_argon2id_hash(value: str) -> bool:
    return value.startswith("$argon2id$")


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password("nexora-timing-equaliser-not-a-credential")


def burn_verification(password: str) -> None:
    """Spend the same work as a real verification (unknown or disabled user: no timing oracle)."""
    verify_password(_dummy_hash(), password)
