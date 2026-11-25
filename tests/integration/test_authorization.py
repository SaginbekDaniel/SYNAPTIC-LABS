"""Role-based authorization (backlog B-011, finding H-09).

Server-side only: every case sends the request a client with the given role would send and checks what
the API does. The UI hiding controls is covered separately and is never relied on here.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from nexora.analytics.config import default_config
from nexora.api.deps import PUBLIC_API_PATHS, api_routes, minimum_role
from nexora.api.main import create_app
from nexora.auth import cli, roles, service
from nexora.persistence import orm
from nexora.persistence.db import session_factory
from nexora.settings import get_settings
from nexora.worker.runner import drain
from tests.auth_helpers import BASE_URL, ensure_user, login

pytestmark = pytest.mark.integration

# The authorization matrix (MASTER_HANDOFF §11). Every state-changing route, with its minimum role;
# every other /api route is readable by every role. Changing a line here is a policy change.
WRITES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/auth/logout"): "viewer",
    ("POST", "/api/v1/lab/datasets"): "analyst",
    ("POST", "/api/v1/analysis/jobs"): "analyst",
    ("POST", "/api/v1/cases"): "analyst",
    ("POST", "/api/v1/cases/{case_id}/decisions"): "analyst",
    ("POST", "/api/v1/cases/{case_id}/notes"): "analyst",
    ("POST", "/api/v1/datasets/import"): "admin",  # decision D-11
}


def _user(factory, role: str) -> tuple[str, str]:
    name, password = f"{role}.{uuid.uuid4().hex[:8]}", f"pw-{uuid.uuid4().hex}"
    ensure_user(factory, name, password, role=role)
    return name, password


def _signed_in(settings, factory, role: str) -> Iterator[TestClient]:
    name, password = _user(factory, role)
    with TestClient(create_app(settings), base_url=BASE_URL) as c:
        login(c, name, password)
        c.headers["X-Test-User"] = name  # not read by the server; lets a test find the account again
        yield c


@pytest.fixture()
def viewer(settings, factory) -> Iterator[TestClient]:
    yield from _signed_in(settings, factory, "viewer")


@pytest.fixture()
def analyst(settings, factory) -> Iterator[TestClient]:
    yield from _signed_in(settings, factory, "analyst")


def _alert_id(client: TestClient, settings) -> str:
    ds = client.post("/api/v1/lab/datasets", json={"suite": "demo-v1", "seed": 7311}).json()["dataset"]["id"]
    assert client.post("/api/v1/analysis/jobs", json={"dataset_id": ds}).status_code == 202
    drain(session_factory(settings.database_url), config=default_config())
    items = client.get("/api/v1/alerts", params={"dataset_id": ds}).json()["items"]
    assert items, "the demo dataset produces alerts"
    return str(items[0]["id"])


def _error_code(r) -> str | None:
    if not r.headers.get("content-type", "").startswith("application/json"):
        return None
    body = r.json()
    return body.get("error", {}).get("code") if isinstance(body, dict) else None


def _count(factory, model) -> int:
    with factory() as s:
        return int(s.scalar(select(func.count()).select_from(model)) or 0)


# -- the matrix ----------------------------------------------------------------------------------
def test_every_route_declares_the_documented_minimum_role(settings):
    declared = {}
    for path, methods, route in api_routes(create_app(settings)):
        for method in methods:
            if path not in PUBLIC_API_PATHS:
                declared[(method, path)] = minimum_role(route)
    assert len(declared) >= 28
    writes = {k: v for k, v in declared.items() if k[0] != "GET"}
    assert writes == WRITES
    assert {v for k, v in declared.items() if k[0] == "GET"} == {"viewer"}


@pytest.mark.parametrize("role", roles.ROLES)
def test_each_role_is_refused_exactly_the_routes_above_it(settings, factory, role):
    """Every operation from OpenAPI, for every role: 403 FORBIDDEN_ROLE if and only if the role is below the
    route's minimum. Refusals look identical and name neither the requirement nor the caller's role."""
    settings.allow_csv_import = True  # otherwise the import gate answers first for every role
    paths = {p: ops for p, ops in create_app(settings).openapi()["paths"].items() if p.startswith("/api/")}
    clients = _signed_in(settings, factory, role)
    client = next(clients)
    refused = allowed = 0
    try:
        for route_path, operations in paths.items():
            if route_path in PUBLIC_API_PATHS or route_path == "/api/v1/auth/logout":
                continue  # sign-in is public; logout is checked below (it ends this session)
            path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), route_path)
            for method in operations:
                minimum = WRITES.get((method.upper(), route_path), "viewer")
                r = client.request(method.upper(), path, json={})
                code = _error_code(r)
                if roles.allows(role, minimum):
                    assert code != "FORBIDDEN_ROLE", (role, method, route_path)
                    assert r.status_code != 401, (role, method, route_path)
                    allowed += 1
                else:
                    assert r.status_code == 403 and code == "FORBIDDEN_ROLE", (role, method, route_path, r.text)
                    message = r.json()["error"]["message"]
                    assert not any(name in message for name in roles.ROLES), message
                    refused += 1
        assert client.post("/api/v1/auth/logout").status_code == 204  # every role may end its own session
    finally:
        settings.allow_csv_import = False
        clients.close()
    expected_refused = sum(not roles.allows(role, m) for m in WRITES.values())
    assert refused == expected_refused and allowed > 20


# -- no side effects -----------------------------------------------------------------------------
def test_a_viewer_reads_everything_and_changes_nothing(viewer, analyst, settings, factory):
    alert_id = _alert_id(analyst, settings)
    case = analyst.post("/api/v1/cases", json={"alert_id": alert_id}).json()

    for path in ("/api/v1/datasets", f"/api/v1/alerts/{alert_id}", f"/api/v1/cases/{case['id']}", "/api/v1/evaluation"):
        assert viewer.get(path).status_code == 200, path
    assert viewer.get(f"/api/v1/cases/{case['id']}/audit").status_code == 200

    before = {m.__name__: _count(factory, m) for m in (orm.Dataset, orm.Case, orm.AuditEvent)}
    jobs_before = _count(factory, orm.AnalysisJob)
    attempts = [
        ("/api/v1/lab/datasets", {"suite": "demo-v1", "seed": 99}),
        ("/api/v1/analysis/jobs", {"dataset_id": str(uuid.uuid4())}),
        ("/api/v1/cases", {"alert_id": alert_id}),
        (f"/api/v1/cases/{case['id']}/decisions", {"to_status": "closed", "expected_version": 1, "reason": "viewer"}),
        (f"/api/v1/cases/{case['id']}/notes", {"body": "viewer note"}),
    ]
    for path, body in attempts:
        r = viewer.post(path, json=body)
        assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN_ROLE", (path, r.text)
    after = {m.__name__: _count(factory, m) for m in (orm.Dataset, orm.Case, orm.AuditEvent)}
    assert after == before and _count(factory, orm.AnalysisJob) == jobs_before
    assert viewer.get(f"/api/v1/cases/{case['id']}").json() == analyst.get(f"/api/v1/cases/{case['id']}").json()


def test_authentication_and_csrf_are_checked_before_the_role(viewer, settings):
    csrf = viewer.headers.pop("X-CSRF-Token")
    try:
        r = viewer.post("/api/v1/cases", json={})
        assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    finally:
        viewer.headers["X-CSRF-Token"] = csrf
    viewer.cookies.clear()
    r = viewer.post("/api/v1/cases", json={})
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"


# -- escalation ----------------------------------------------------------------------------------
def test_no_api_input_can_carry_a_role(settings):
    """Vertical escalation over HTTP is impossible by construction: no request body or parameter has a role,
    and no route manages users. Roles change only through the operator CLI."""
    spec = create_app(settings).openapi()
    for path, operations in spec["paths"].items():
        assert "user" not in path.replace("/auth/", "/"), path
        for op in operations.values():
            assert all(p["name"] != "role" for p in op.get("parameters", [])), path
    request_schemas = {
        ref.rsplit("/", 1)[-1]
        for ops in spec["paths"].values()
        for op in ops.values()
        for content in op.get("requestBody", {}).get("content", {}).values()
        for ref in [content["schema"].get("$ref", "")]
        if ref
    }
    for name in request_schemas:
        assert "role" not in spec["components"]["schemas"][name].get("properties", {}), name


def test_login_ignores_a_role_in_the_request(anon_client, factory):
    name, password = _user(factory, "viewer")
    r = anon_client.post("/api/v1/auth/login", json={"username": name, "password": password, "role": "admin"})
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert r.json()["user"]["role"] == "viewer"


def test_the_role_is_read_per_request_not_from_the_session(analyst, factory):
    """A role lowered behind an open session (here directly in the database, so no session is ended)
    applies to that session's very next request."""
    name = analyst.headers["X-Test-User"]
    assert analyst.post("/api/v1/lab/datasets", json={"suite": "demo-v1", "seed": 5}).status_code == 201
    with factory() as s:
        s.execute(update(orm.User).where(orm.User.username == name).values(role="viewer"))
        s.commit()
    r = analyst.post("/api/v1/lab/datasets", json={"suite": "demo-v1", "seed": 6})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert analyst.get("/api/v1/auth/me").json()["user"]["role"] == "viewer"


def test_set_role_ends_sessions_and_is_audited(analyst, factory):
    name = analyst.headers["X-Test-User"]
    with factory() as s:
        assert service.set_role(s, username=name, role="analyst") == 0  # unchanged: no-op, no event
        ended = service.set_role(s, username=name, role="viewer")
        s.commit()
    assert ended == 1
    r = analyst.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"
    with factory() as s:
        events = s.scalars(
            select(orm.AuditEvent).where(orm.AuditEvent.action == "user.set_role", orm.AuditEvent.entity_id == name)
        ).all()
        assert [(e.actor, e.before_json, e.after_json) for e in events] == [
            ("operator-cli", {"role": "analyst"}, {"role": "viewer", "sessions_revoked": 1})
        ]
        user = s.scalar(select(orm.User).where(orm.User.username == name))
        assert user is not None and user.role == "viewer"


# -- accounts, legacy rows, invalid roles --------------------------------------------------------
def test_accounts_default_to_analyst_and_reject_unknown_roles(factory):
    with factory() as s:
        user = service.create_user(s, username=f"legacy.{uuid.uuid4().hex[:6]}", password=f"pw-{uuid.uuid4().hex}")
        assert user.role == "analyst"
        with pytest.raises(Exception, match="role must be one of"):
            service.create_user(s, username=f"root.{uuid.uuid4().hex[:6]}", password="x" * 20, role="root")
        with pytest.raises(Exception, match="role must be one of"):
            service.set_role(s, username=user.username, role="superuser")
        s.rollback()
    with factory() as s:  # the database refuses an unknown role even past the service layer
        uid = uuid.uuid4()
        s.execute(
            text("INSERT INTO users (id, username, display_name, password_hash) VALUES (:id, :u, 'L', 'x')"),
            {"id": uid, "u": f"raw.{uuid.uuid4().hex[:6]}"},
        )
        assert s.scalar(select(orm.User.role).where(orm.User.id == uid)) == "analyst"  # server default
        with pytest.raises(IntegrityError):
            s.execute(update(orm.User).where(orm.User.id == uid).values(role="root"))
            s.flush()
        s.rollback()


def test_an_unknown_role_is_allowed_nothing():
    assert not roles.allows("root", "viewer") and not roles.allows("", "viewer")
    assert roles.allows("admin", "analyst") and not roles.allows("viewer", "analyst")


@pytest.fixture()
def cli_env(db_url, monkeypatch):
    monkeypatch.setenv("NEXORA_DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_cli_creates_with_a_role_and_changes_it(cli_env, capsys):
    import io

    name = "cli.role." + uuid.uuid4().hex[:6]
    cli_env.setattr("sys.stdin", io.StringIO(f"pw-{uuid.uuid4().hex}\n"))
    assert cli.main(["create-user", name, "--password-stdin", "--role", "viewer"]) == 0
    assert f"created user {name} (viewer)" in capsys.readouterr().out
    assert cli.main(["set-role", name, "admin"]) == 0
    assert cli.main(["list-users"]) == 0
    assert f"{name}\tadmin\tactive" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["set-role", name, "root"])  # argparse refuses an unknown role
