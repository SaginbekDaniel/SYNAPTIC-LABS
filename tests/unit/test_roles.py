"""Role ordering and the build-time deny-by-default check (B-011). No database needed."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI

from nexora.api.deps import api_routes, check_route_roles, declared_role, minimum_role, requires
from nexora.auth import roles


@pytest.mark.parametrize(
    ("role", "minimum", "allowed"),
    [
        ("viewer", "viewer", True),
        ("viewer", "analyst", False),
        ("viewer", "admin", False),
        ("analyst", "viewer", True),
        ("analyst", "analyst", True),
        ("analyst", "admin", False),
        ("admin", "viewer", True),
        ("admin", "admin", True),
        ("Admin", "viewer", False),  # roles are exact strings
        ("root", "viewer", False),  # unknown: nothing
    ],
)
def test_roles_are_ordered_and_fail_closed(role: str, minimum: roles.Role, allowed: bool):
    assert roles.allows(role, minimum) is allowed


def test_default_role_keeps_pre_role_behaviour():
    assert roles.DEFAULT_ROLE == "analyst" and roles.ROLES == ("viewer", "analyst", "admin")


def _app(*, declare_write: bool) -> FastAPI:
    router = APIRouter(prefix="/api/v1")

    @router.get("/things")
    def read() -> None: ...

    deps = [requires("analyst")] if declare_write else []

    @router.post("/things", dependencies=deps)
    def write() -> None: ...

    @router.post("/things/{tid}/purge", dependencies=[requires("analyst"), requires("admin")])
    def purge(tid: str) -> None: ...

    app = FastAPI()
    app.include_router(router)
    return app


def test_a_write_route_without_a_declared_role_stops_the_app_from_building():
    with pytest.raises(RuntimeError, match=r"POST /api/v1/things"):
        check_route_roles(_app(declare_write=False))
    check_route_roles(_app(declare_write=True))


def test_routes_in_included_routers_are_found_and_the_strictest_declaration_wins():
    found = {(path, tuple(sorted(methods))): route for path, methods, route in api_routes(_app(declare_write=True))}
    assert set(found) == {
        ("/api/v1/things", ("GET",)),
        ("/api/v1/things", ("POST",)),
        ("/api/v1/things/{tid}/purge", ("POST",)),
    }
    assert declared_role(found[("/api/v1/things", ("GET",))]) is None
    assert minimum_role(found[("/api/v1/things", ("GET",))]) == "viewer"
    assert minimum_role(found[("/api/v1/things", ("POST",))]) == "analyst"
    assert minimum_role(found[("/api/v1/things/{tid}/purge", ("POST",))]) == "admin"


def test_an_app_without_api_routes_is_not_silently_accepted():
    with pytest.raises(RuntimeError, match="no /api routes"):
        check_route_roles(FastAPI())
