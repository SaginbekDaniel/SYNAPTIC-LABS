from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from nexora.application.errors import Forbidden, Invalid, Unauthorized
from nexora.auth import service as auth
from nexora.auth import tokens
from nexora.settings import Settings

CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# The only /api routes reachable without a session. Everything else is protected by default:
# a new router needs no opt-in, and tests/integration/test_auth.py enumerates every route.
PUBLIC_API_PATHS = frozenset({"/api/v1/auth/login", "/api/v1/auth/session"})


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# scope="function": the code after ``yield`` (the commit) runs before the response is sent. With the
# default request scope FastAPI commits *after* responding, so a client's immediate follow-up request
# could miss the write it was just told about (audit F-14, seen as DATASET_NOT_FOUND on CI).
SessionDep = Annotated[Session, Depends(get_session, scope="function")]


def session_cookie_name(settings: Settings) -> str:
    # __Host- prefix: browsers only accept it with Secure, Path=/ and no Domain, so the cookie can
    # neither be set by a sibling subdomain nor scoped wider than this origin.
    return "__Host-nexora_session" if settings.session_cookie_secure else "nexora_session"


def presented_token(request: Request) -> str | None:
    return request.cookies.get(session_cookie_name(request.app.state.settings))


def client_address(request: Request) -> str:
    """Client address for throttling. Behind the gateway (token verified by middleware) the last
    X-Forwarded-For hop is the one Nginx appended after its own trusted real-IP resolution."""
    settings: Settings = request.app.state.settings
    if settings.gateway_token:
        hops = [h.strip() for h in request.headers.get("X-Forwarded-For", "").split(",") if h.strip()]
        if hops:
            return hops[-1][:64]
    return (request.client.host if request.client else "unknown")[:64]


def _request_origin(request: Request) -> str:
    settings: Settings = request.app.state.settings
    scheme = request.url.scheme
    if settings.gateway_token:  # only then is X-Forwarded-Proto known to come from our gateway
        scheme = request.headers.get("X-Forwarded-Proto", scheme).split(",")[0].strip() or scheme
    return f"{scheme}://{request.headers.get('host', '')}".lower()


def check_origin(request: Request) -> None:
    """Reject state-changing requests initiated by another site (defence in depth next to the
    SameSite=Strict cookie and the CSRF token)."""
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin is not None:
        # Origins allowed by CORS are trusted by definition (local dev servers; empty on Railway).
        configured = f"{settings.trusted_origins},{settings.cors_origins}"
        trusted = {o.strip().rstrip("/").lower() for o in configured.split(",") if o.strip()}
        trusted.add(_request_origin(request))
        if origin.rstrip("/").lower() not in trusted:
            raise Forbidden("ORIGIN_NOT_ALLOWED", "request origin is not allowed")
    elif request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise Forbidden("ORIGIN_NOT_ALLOWED", "cross-site request rejected")


def enforce_authentication(request: Request) -> None:
    """Global dependency (see create_app): every /api route requires a valid server-side session,
    and every state-changing request additionally a trusted origin and the session's CSRF token."""
    path = request.url.path
    if not path.startswith("/api/"):
        return  # health probes only; the API serves nothing else
    unsafe = request.method not in _SAFE_METHODS
    if path in PUBLIC_API_PATHS:
        if unsafe:
            check_origin(request)
        return
    token = presented_token(request)
    settings: Settings = request.app.state.settings
    with request.app.state.session_factory() as s:
        principal = auth.authenticate(s, settings, token)
        s.commit()
    if principal is None:
        raise Unauthorized(auth.AUTH_REQUIRED, "authentication required")
    if unsafe:
        check_origin(request)
        presented = request.headers.get(CSRF_HEADER, "")
        if not (token and presented and tokens.csrf_matches(token, presented)):
            raise Forbidden("CSRF_FAILED", "missing or invalid CSRF token")
    request.state.principal = principal


def current_principal(request: Request) -> auth.Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, auth.Principal):  # unreachable for protected routes; fail closed
        raise Unauthorized(auth.AUTH_REQUIRED, "authentication required")
    return principal


PrincipalDep = Annotated[auth.Principal, Depends(current_principal)]


def actor(request: Request) -> str:
    """The analyst identity recorded on audit events: the validated session's user, never a value
    supplied by the client."""
    return current_principal(request).username


def request_id(request: Request) -> str:
    return str(request.state.request_id)


def parse_uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise Invalid("INVALID_ID", f"{what} must be a UUID", {"field": what}) from exc
