"""Opaque session tokens and the session-bound CSRF token."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

TOKEN_BYTES = 32  # 256 bits from the OS CSPRNG
_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{43}$")  # base64url of 32 bytes, no padding
_CSRF_CONTEXT = b"nexora-csrf-v1"


def new_session_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def well_formed(token: str) -> bool:
    return bool(_TOKEN_SHAPE.fullmatch(token))


def token_digest(token: str) -> str:
    """At-rest form of a session token. A fast hash is appropriate: the token has 256 bits of entropy,
    so a leaked digest cannot be reversed, and lookups stay O(1) through the unique index."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def csrf_token(session_token: str) -> str:
    """Synchronizer token derived from the session secret: only a holder of the HttpOnly cookie's value
    (the server) can compute it, it changes with every session, and nothing extra is stored."""
    return hmac.new(session_token.encode("ascii"), _CSRF_CONTEXT, hashlib.sha256).hexdigest()


def csrf_matches(session_token: str, presented: str) -> bool:
    return hmac.compare_digest(csrf_token(session_token).encode(), presented.encode("utf-8", "replace"))
