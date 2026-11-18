"""Sign-in helpers for API tests (disposable databases only)."""

from __future__ import annotations

# Test-only credentials for a disposable database; never used anywhere else.
ANALYST = "analyst.one"
ANALYST_PASSWORD = "test-only-password-analyst-one"
BASE_URL = "https://testserver"  # HTTPS so the Secure __Host- session cookie round-trips


def ensure_user(
    factory, username: str = ANALYST, password: str = ANALYST_PASSWORD, display_name: str | None = None
) -> None:
    from sqlalchemy import select

    from nexora.auth import service
    from nexora.persistence import orm

    with factory() as s:
        if s.scalar(select(orm.User.id).where(orm.User.username == username)) is None:
            service.create_user(s, username=username, password=password, display_name=display_name)
            s.commit()


def login(client, username: str = ANALYST, password: str = ANALYST_PASSWORD) -> dict:
    """Sign in through the API and make the client send the session's CSRF token on writes."""
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    return body
