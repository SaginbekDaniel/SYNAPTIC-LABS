from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from nexora.api.identity import authenticate
from nexora.application.errors import Invalid


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session: Session = factory()
    try:
        if request.app.state.authenticated_analytics and not request.url.path.startswith("/api/v1/sandbox/"):
            principal = authenticate(request, request.headers.get("Authorization"))
            if principal.role not in {"analyst", "reviewer", "administrator", "service"}:
                raise HTTPException(403, "analyst authorization required")
            if (
                principal.role == "service"
                and request.method != "GET"
                and not request.url.path.endswith(("/datasets/import", "/analysis/jobs"))
            ):
                raise HTTPException(403, "service scope does not permit this operation")
            request.state.analytics_principal = principal
            session.info["tenant"] = principal.tenant
        else:
            session.info["demo_scope"] = True
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


def actor(request: Request) -> str:
    """DEMO MODE: every request acts as the configured local analyst identity.

    This is explicitly not production authentication (spec §16.5)."""
    principal = getattr(request.state, "analytics_principal", None)
    return str(principal.subject if principal is not None else request.app.state.settings.demo_analyst)


def source_scope(request: Request) -> str:
    actor_id = actor(request)
    principal = getattr(request.state, "analytics_principal", None)
    return actor_id if principal is None else f"{len(principal.tenant)}:{principal.tenant}:{actor_id}"


def require_case_reviewer(request: Request) -> None:
    principal = getattr(request.state, "analytics_principal", None)
    if principal is not None and principal.role not in {"reviewer", "administrator"}:
        raise HTTPException(403, "reviewer authorization required")


def request_id(request: Request) -> str:
    return str(request.state.request_id)


def parse_uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise Invalid("INVALID_ID", f"{what} must be a UUID", {"field": what}) from exc
