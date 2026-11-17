from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from nexora.application.errors import Invalid


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


def actor(request: Request) -> str:
    """DEMO MODE: every request acts as the configured local analyst identity.

    This is explicitly not production authentication (spec §16.5)."""
    return str(request.app.state.settings.demo_analyst)


def request_id(request: Request) -> str:
    return str(request.state.request_id)


def parse_uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise Invalid("INVALID_ID", f"{what} must be a UUID", {"field": what}) from exc
