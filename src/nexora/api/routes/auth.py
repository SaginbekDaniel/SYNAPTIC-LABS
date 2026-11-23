"""Sign-in, session bootstrap, current session, sign-out. Only POST /auth/login and GET /auth/session
are reachable without a session (see deps.PUBLIC_API_PATHS)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Request, Response

from nexora.api import schemas
from nexora.api.deps import (
    PrincipalDep,
    SessionDep,
    client_address,
    presented_token,
    request_id,
    requires,
    session_cookie_name,
)
from nexora.application.errors import Invalid, Unauthorized
from nexora.auth import service as auth
from nexora.settings import Settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": schemas.ErrorEnvelope},
    403: {"model": schemas.ErrorEnvelope},
    429: {"model": schemas.ErrorEnvelope},
}


def _session_body(principal: auth.Principal, settings: Settings) -> dict[str, Any]:
    return {
        "user": {"username": principal.username, "display_name": principal.display_name, "role": principal.role},
        "csrf_token": principal.csrf_token,
        "expires_at": principal.session_expires_at,
        "idle_timeout_seconds": settings.session_idle_minutes * 60,
    }


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        session_cookie_name(settings), path="/", secure=settings.session_cookie_secure, httponly=True, samesite="strict"
    )


@router.post("/login", response_model=schemas.AuthSession, responses=_ERRORS)
def login(body: schemas.LoginRequest, request: Request, response: Response, session: SessionDep) -> Any:
    # A JSON body forces a CORS preflight for cross-origin callers; form posts cannot reach this route.
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise Invalid("CONTENT_TYPE_REQUIRED", "sign-in requires application/json")
    settings: Settings = request.app.state.settings
    try:
        result = auth.sign_in(
            session,
            settings,
            username=body.username,
            password=body.password.get_secret_value(),
            client=client_address(request),
            previous_token=presented_token(request),
            request_id=request_id(request),
        )
    except Unauthorized:
        session.commit()  # keep the failed attempt: it feeds the brute-force throttle
        raise
    ttl = int((result.principal.session_expires_at - dt.datetime.now(dt.UTC)).total_seconds())
    response.set_cookie(
        session_cookie_name(settings),
        result.token,
        max_age=max(ttl, 0),
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return _session_body(result.principal, settings)


@router.get("/session", response_model=schemas.SessionState)
def session_state(request: Request, response: Response) -> Any:
    """Whether the browser's cookie is a live session. Public, read-only, reveals nothing without a
    valid cookie; lets the sign-in page load without a failing (console-logged) 401 request."""
    settings: Settings = request.app.state.settings
    token = presented_token(request)
    with request.app.state.session_factory() as s:
        principal = auth.authenticate(s, settings, token)
        s.commit()
    if principal is None:
        if token is not None:
            clear_session_cookie(response, settings)
        return {"authenticated": False, "session": None}
    return {"authenticated": True, "session": _session_body(principal, settings)}


@router.get("/me", response_model=schemas.AuthSession, responses=_ERRORS)
def me(principal: PrincipalDep, request: Request) -> Any:
    return _session_body(principal, request.app.state.settings)


@router.post("/logout", status_code=204, responses=_ERRORS, dependencies=[requires("viewer")])
def logout(principal: PrincipalDep, request: Request, response: Response, session: SessionDep) -> Response:
    token = presented_token(request) or ""
    auth.sign_out(session, principal, token=token, request_id=request_id(request))
    response.status_code = 204
    clear_session_cookie(response, request.app.state.settings)
    return response
