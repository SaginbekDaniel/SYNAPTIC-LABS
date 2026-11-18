"""Server-side authentication: sessions, CSRF, origin checks, throttling, attribution, operator CLI."""

from __future__ import annotations

import datetime as dt
import logging
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from nexora.analytics.config import default_config
from nexora.api.deps import PUBLIC_API_PATHS
from nexora.api.main import GATEWAY_TOKEN_HEADER, create_app
from nexora.auth import cli, passwords, service
from nexora.persistence import orm
from nexora.persistence.db import session_factory
from nexora.settings import Settings, get_settings
from nexora.worker.runner import drain
from tests.auth_helpers import BASE_URL, ensure_user, login

pytestmark = pytest.mark.integration

COOKIE = "__Host-nexora_session"


def _new_user(factory, prefix: str = "user") -> tuple[str, str]:
    name, password = f"{prefix}.{uuid.uuid4().hex[:8]}", f"pw-{uuid.uuid4().hex}"
    ensure_user(factory, name, password, display_name=f"{prefix.title()} Analyst")
    return name, password


def _client(settings: Settings, **headers: str) -> TestClient:
    c = TestClient(create_app(settings), base_url=BASE_URL)
    c.headers.update(headers)
    return c


def _session_row(factory, token: str) -> orm.AuthSession:
    from nexora.auth.tokens import token_digest

    with factory() as s:
        row = s.scalar(select(orm.AuthSession).where(orm.AuthSession.token_hash == token_digest(token)))
        assert row is not None
        return row


# -- sign-in -------------------------------------------------------------------------------------
def test_successful_login_sets_a_hardened_session_cookie(anon_client, factory):
    name, password = _new_user(factory)
    r = anon_client.post("/api/v1/auth/login", json={"username": name.upper(), "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"] == {"username": name, "display_name": "User Analyst"}
    assert re.fullmatch(r"[0-9a-f]{64}", body["csrf_token"])
    assert body["idle_timeout_seconds"] == 120 * 60
    assert password not in r.text
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert attribute.lower() in cookie.lower(), attribute
    assert "domain=" not in cookie.lower()
    assert r.headers["cache-control"] == "no-store"
    me = anon_client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["user"]["username"] == name
    assert me.json()["csrf_token"] == body["csrf_token"]


def test_only_a_hash_of_the_session_token_is_stored(anon_client, factory):
    name, password = _new_user(factory)
    login(anon_client, name, password)
    token = anon_client.cookies[COOKIE]
    row = _session_row(factory, token)
    assert row.token_hash != token and token not in row.token_hash
    with factory() as s:
        user = s.scalar(select(orm.User).where(orm.User.username == name))
        assert user is not None and user.password_hash.startswith("$argon2id$") and password not in user.password_hash


@pytest.mark.parametrize("case", ["wrong_password", "unknown_user", "disabled_user"])
def test_failed_sign_in_is_generic_and_does_not_enumerate_accounts(anon_client, factory, case):
    name, password = _new_user(factory, "enum")
    if case == "disabled_user":
        with factory() as s:
            service.set_active(s, username=name, active=False)
            s.commit()
    username = "nobody-" + uuid.uuid4().hex[:8] if case == "unknown_user" else name
    attempt = password if case == "disabled_user" else "not-the-password-123"
    r = anon_client.post("/api/v1/auth/login", json={"username": username, "password": attempt})
    assert r.status_code == 401
    err = r.json()["error"]
    assert (err["code"], err["message"], err["details"]) == ("INVALID_CREDENTIALS", "invalid user name or password", {})
    assert "set-cookie" not in r.headers
    assert attempt not in r.text


def test_login_requires_a_json_body(anon_client, factory):
    # A form-encoded or text body (what a cross-site <form> can send without a CORS preflight) never signs in.
    name, password = _new_user(factory)
    for content_type, content in (
        ("text/plain", f'{{"username":"{name}","password":"{password}"}}'),
        ("application/x-www-form-urlencoded", f"username={name}&password={password}"),
    ):
        r = anon_client.post("/api/v1/auth/login", content=content, headers={"Content-Type": content_type})
        assert r.status_code == 422, content_type
        assert COOKIE not in anon_client.cookies


def test_validation_errors_never_echo_the_password(anon_client):
    secret = "s3cret-" + uuid.uuid4().hex
    r = anon_client.post("/api/v1/auth/login", json={"username": "", "password": secret})
    assert r.status_code == 422
    assert secret not in r.text


# -- sessions ------------------------------------------------------------------------------------
@pytest.mark.parametrize("cookie", ["", "x", "not a token", "A" * 43 + "=", "A" * 4000])
def test_malformed_or_unknown_session_is_rejected(settings, cookie):
    with _client(settings) as c:
        c.cookies.set(COOKIE, cookie)
        r = c.get("/api/v1/datasets")
        assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"


def test_unknown_well_formed_token_is_rejected_and_the_cookie_cleared(settings):
    with _client(settings) as c:
        c.cookies.set(COOKIE, "A" * 43)
        r = c.get("/api/v1/auth/me")
        assert r.status_code == 401
        assert f"{COOKIE}=" in r.headers["set-cookie"] and "max-age=0" in r.headers["set-cookie"].lower()


@pytest.mark.parametrize("expiry", ["absolute", "idle"])
def test_expired_session_is_rejected(anon_client, factory, expiry):
    name, password = _new_user(factory)
    login(anon_client, name, password)
    token = anon_client.cookies[COOKIE]
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=13 if expiry == "absolute" else 3)
    column = "expires_at" if expiry == "absolute" else "last_seen_at"
    with factory() as s:
        s.execute(
            update(orm.AuthSession).where(orm.AuthSession.id == _session_row(factory, token).id).values({column: past})
        )
        s.commit()
    r = anon_client.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"


def test_activity_extends_an_idle_session(anon_client, factory):
    name, password = _new_user(factory)
    login(anon_client, name, password)
    token = anon_client.cookies[COOKIE]
    almost_idle = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=119)
    with factory() as s:
        s.execute(
            update(orm.AuthSession)
            .where(orm.AuthSession.id == _session_row(factory, token).id)
            .values(last_seen_at=almost_idle)
        )
        s.commit()
    assert anon_client.get("/api/v1/auth/me").status_code == 200
    assert _session_row(factory, token).last_seen_at > almost_idle + dt.timedelta(minutes=100)


def test_operator_revocation_and_password_change_end_sessions(anon_client, factory):
    name, password = _new_user(factory)
    login(anon_client, name, password)
    with factory() as s:
        assert service.revoke_sessions(s, username=name) == 1
        s.commit()
    assert anon_client.get("/api/v1/auth/me").status_code == 401
    login(anon_client, name, password)
    with factory() as s:
        assert service.set_password(s, username=name, password="a-brand-new-password-1") == 1
        s.commit()
    assert anon_client.get("/api/v1/auth/me").status_code == 401
    r = anon_client.post("/api/v1/auth/login", json={"username": name, "password": password})
    assert r.status_code == 401


def test_logout_revokes_the_session_server_side(anon_client, factory):
    name, password = _new_user(factory)
    login(anon_client, name, password)
    token = anon_client.cookies[COOKIE]
    r = anon_client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert "max-age=0" in r.headers["set-cookie"].lower()
    assert _session_row(factory, token).revoked_at is not None
    # Replaying the captured cookie after logout does not work.
    anon_client.cookies.set(COOKIE, token)
    for method, path in [("GET", "/api/v1/auth/me"), ("GET", "/api/v1/datasets"), ("POST", "/api/v1/lab/datasets")]:
        r = anon_client.request(method, path, json={"suite": "demo-v1", "seed": 1})
        assert r.status_code == 401, (method, path)


def test_sign_in_replaces_any_presented_session_fixation(settings, factory):
    victim, victim_pw = _new_user(factory, "victim")
    attacker, attacker_pw = _new_user(factory, "attacker")
    with _client(settings) as attacker_client:
        login(attacker_client, attacker, attacker_pw)
        planted = attacker_client.cookies[COOKIE]
    with _client(settings) as victim_client:
        victim_client.cookies.set(COOKIE, planted)  # e.g. injected by a malicious subdomain
        r = victim_client.post("/api/v1/auth/login", json={"username": victim, "password": victim_pw})
        assert r.status_code == 200 and r.json()["user"]["username"] == victim
        issued = r.cookies[COOKIE]
        assert issued != planted
    # The planted session is gone, and it never became the victim's identity.
    assert _session_row(factory, planted).revoked_reason == "replaced_by_sign_in"
    with _client(settings) as c:
        c.cookies.set(COOKIE, planted)
        assert c.get("/api/v1/auth/me").status_code == 401


# -- CSRF and origin -----------------------------------------------------------------------------
def test_state_changing_requests_need_the_session_csrf_token(settings, factory):
    a, a_pw = _new_user(factory)
    b, b_pw = _new_user(factory)
    with _client(settings) as other:
        foreign = login(other, b, b_pw)["csrf_token"]
    with _client(settings) as c:
        own = login(c, a, a_pw)["csrf_token"]
        body = {"suite": "funnel-only-v1", "seed": 77}
        for header in (None, "", "0" * 64, foreign):
            headers = {"X-CSRF-Token": header} if header is not None else {}
            c.headers.pop("X-CSRF-Token", None)
            r = c.post("/api/v1/lab/datasets", json=body, headers=headers)
            assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED", header
        assert c.post("/api/v1/auth/logout").status_code == 403  # logout is a write too
        assert c.post("/api/v1/lab/datasets", json=body, headers={"X-CSRF-Token": own}).status_code == 201
        # Reads need no token.
        assert c.get("/api/v1/datasets").status_code == 200


def test_cross_origin_writes_are_rejected(settings, factory):
    name, password = _new_user(factory)
    with _client(settings) as c:
        login(c, name, password)
        for headers in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}, {"Origin": "null"}):
            r = c.post("/api/v1/lab/datasets", json={"suite": "funnel-only-v1", "seed": 5}, headers=headers)
            assert r.status_code == 403 and r.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED", headers
        assert (
            c.post(
                "/api/v1/lab/datasets", json={"suite": "funnel-only-v1", "seed": 5}, headers={"Origin": BASE_URL}
            ).status_code
            == 201
        )
    with _client(settings) as c:  # login CSRF
        r = c.post(
            "/api/v1/auth/login",
            json={"username": name, "password": password},
            headers={"Origin": "https://evil.example"},
        )
        assert r.status_code == 403 and COOKIE not in c.cookies


def test_cors_origins_are_trusted_for_writes(db_url, factory):
    # Local dev: Vite proxies with changeOrigin, so Host is the API's; the page origin is in CORS.
    name, password = _new_user(factory)
    settings = Settings(database_url=db_url, cors_origins="http://127.0.0.1:5173")
    with _client(settings) as c:
        r = c.post(
            "/api/v1/auth/login",
            json={"username": name, "password": password},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert r.status_code == 200
        r = c.post(
            "/api/v1/auth/login",
            json={"username": name, "password": password},
            headers={"Origin": "http://127.0.0.1:5174"},
        )
        assert r.status_code == 403


def test_trusted_origins_and_forwarded_scheme_behind_the_gateway(db_url, factory):
    name, password = _new_user(factory)
    settings = Settings(database_url=db_url, gateway_token="tok", trusted_origins="https://nexora.example")
    with _client(settings, **{GATEWAY_TOKEN_HEADER: "tok"}) as c:
        # The gateway speaks plain HTTP to the API; the public origin is https (X-Forwarded-Proto).
        c.base_url = c.base_url.copy_with(scheme="http")
        c.headers["X-Forwarded-Proto"] = "https"
        c.headers["X-Forwarded-For"] = "198.51.100.9"
        for origin in ("https://testserver", "https://nexora.example"):
            r = c.post("/api/v1/auth/login", json={"username": name, "password": password}, headers={"Origin": origin})
            assert r.status_code == 200, (origin, r.text)


# -- every API route is protected ----------------------------------------------------------------
def test_every_api_route_rejects_anonymous_requests(settings, anon_client):
    # The OpenAPI document lists every mounted operation (it is generated even when docs are not served).
    paths = {p: ops for p, ops in create_app(settings).openapi()["paths"].items() if p.startswith("/api/")}
    assert len(paths) > 15
    checked = 0
    for route_path, operations in paths.items():
        path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), route_path)
        for method in operations:
            r = anon_client.request(method.upper(), path, json={})
            if route_path in PUBLIC_API_PATHS:
                assert r.status_code != 401 or r.json()["error"]["code"] == "INVALID_CREDENTIALS"
                continue
            assert r.status_code == 401, (method, route_path, r.status_code)
            assert r.json()["error"]["code"] == "AUTH_REQUIRED"
            checked += 1
    assert checked >= 20
    # Changing the public surface must be a deliberate, reviewed edit of this line.
    assert {"/api/v1/auth/login", "/api/v1/auth/session"} == PUBLIC_API_PATHS


def test_session_bootstrap_answers_anonymous_callers_without_an_error(anon_client, factory):
    assert anon_client.get("/api/v1/auth/session").json() == {"authenticated": False, "session": None}
    anon_client.cookies.set(COOKIE, "A" * 43)  # dead cookie: reported anonymous and cleared
    r = anon_client.get("/api/v1/auth/session")
    assert r.status_code == 200 and not r.json()["authenticated"] and "max-age=0" in r.headers["set-cookie"].lower()
    anon_client.cookies.clear()
    name, password = _new_user(factory)
    csrf = login(anon_client, name, password)["csrf_token"]
    body = anon_client.get("/api/v1/auth/session").json()
    assert body["authenticated"] and body["session"]["user"]["username"] == name
    assert body["session"]["csrf_token"] == csrf


def test_health_endpoints_reveal_no_identity(anon_client):
    body = anon_client.get("/health/ready").json()
    assert "actor" not in body


# -- attribution ---------------------------------------------------------------------------------
def test_audit_events_and_jobs_carry_the_authenticated_identity(settings, factory):
    first, first_pw = _new_user(factory, "first")
    second, second_pw = _new_user(factory, "second")
    with _client(settings) as c:
        login(c, first, first_pw)
        ds = c.post("/api/v1/lab/datasets", json={"suite": "demo-v1", "seed": 3131}).json()["dataset"]["id"]
        job = c.post("/api/v1/analysis/jobs", json={"dataset_id": ds}).json()
        assert job.get("requested_by", first) == first
        drain(session_factory(settings.database_url), config=default_config())
        alert = c.get("/api/v1/alerts", params={"dataset_id": ds}).json()["items"][0]
        case = c.post("/api/v1/cases", json={"alert_id": alert["id"]}).json()
        # The client cannot name the actor: unknown fields are rejected, not trusted.
        spoof = c.post(f"/api/v1/cases/{case['id']}/notes", json={"body": "x", "actor": "someone-else"})
        assert spoof.status_code == 422
    with _client(settings) as c:
        login(c, second, second_pw)
        r = c.post(
            f"/api/v1/cases/{case['id']}/decisions",
            json={"to_status": "investigating", "expected_version": case["version"], "reason": None},
        )
        assert r.status_code == 200, r.text
        audit = c.get(f"/api/v1/cases/{case['id']}/audit").json()
    assert [e["actor"] for e in audit] == [first, second]
    with factory() as s:
        assert (
            s.scalar(select(orm.AnalysisJob.requested_by).where(orm.AnalysisJob.dataset_id == uuid.UUID(ds))) == first
        )
        actions = s.execute(
            select(orm.AuditEvent.actor, orm.AuditEvent.action).where(
                orm.AuditEvent.action == "auth.sign_in", orm.AuditEvent.actor.in_([first, second])
            )
        ).all()
        assert {a for a, _ in actions} == {first, second}


# -- brute force ---------------------------------------------------------------------------------
def test_repeated_failures_lock_the_name_even_for_unknown_accounts(anon_client, factory):
    name, password = _new_user(factory, "lock")
    ghost = "ghost-" + uuid.uuid4().hex[:8]
    for username in (name, ghost):
        for _ in range(5):
            r = anon_client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password-xx"})
            assert r.status_code == 401
        blocked = anon_client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-password-xx"})
        assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
        assert 0 < int(blocked.headers["Retry-After"]) <= 15 * 60
    # The correct password does not get through a lock (and existence is not revealed either way).
    r = anon_client.post("/api/v1/auth/login", json={"username": name, "password": password})
    assert r.status_code == 429


def test_successful_sign_in_resets_the_name_counter(anon_client, factory):
    name, password = _new_user(factory, "reset")
    for _ in range(4):
        anon_client.post("/api/v1/auth/login", json={"username": name, "password": "wrong-password-xx"})
    login(anon_client, name, password)
    for _ in range(4):
        r = anon_client.post("/api/v1/auth/login", json={"username": name, "password": "wrong-password-xx"})
        assert r.status_code == 401
    login(anon_client, name, password)


def test_one_client_cannot_spray_many_names(db_url):
    settings = Settings(database_url=db_url, gateway_token="tok", login_max_failures_per_client=3)
    with _client(settings, **{GATEWAY_TOKEN_HEADER: "tok", "X-Forwarded-For": "203.0.113.50"}) as c:
        for _ in range(3):
            r = c.post("/api/v1/auth/login", json={"username": "u" + uuid.uuid4().hex[:6], "password": "p" * 12})
            assert r.status_code == 401
        r = c.post("/api/v1/auth/login", json={"username": "u" + uuid.uuid4().hex[:6], "password": "p" * 12})
        assert r.status_code == 429
        # The client key is the gateway-appended hop: a spoofed leading X-Forwarded-For entry does not reset it.
        r = c.post(
            "/api/v1/auth/login",
            json={"username": "u1x", "password": "p" * 12},
            headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.50"},
        )
        assert r.status_code == 429


def test_failed_attempts_store_no_submitted_name_or_password(anon_client, factory, caplog):
    typo = "my-password-typed-as-username-" + uuid.uuid4().hex[:6]
    with caplog.at_level(logging.DEBUG):
        anon_client.post("/api/v1/auth/login", json={"username": typo, "password": typo + "!"})
    assert typo not in caplog.text
    with factory() as s:
        stored = s.scalars(select(orm.LoginAttempt.username_digest)).all()
    assert typo not in stored and all(re.fullmatch(r"[0-9a-f]{64}", d) for d in stored)


# -- migration and operator CLI ------------------------------------------------------------------
def test_usernames_are_stored_normalised(factory):
    with factory() as s:
        user = service.create_user(s, username="  Mixed.Case.User  ", password="long-enough-password")
        assert user.username == "mixed.case.user"
        s.rollback()
    with factory() as s, pytest.raises(Exception, match=r"at least"):
        service.create_user(s, username="shortpw", password="short")


@pytest.fixture()
def cli_env(db_url, monkeypatch):
    monkeypatch.setenv("NEXORA_DATABASE_URL", db_url)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_cli_creates_users_from_stdin_and_never_from_argv(cli_env, capsys, anon_client):
    import io

    name = "cli." + uuid.uuid4().hex[:6]
    cli_env.setattr("sys.stdin", io.StringIO("cli-provided-password-1\n"))
    assert cli.main(["create-user", name, "--password-stdin", "--display-name", "CLI User"]) == 0
    assert "cli-provided-password-1" not in capsys.readouterr().out
    login(anon_client, name, "cli-provided-password-1")
    cli_env.setattr("sys.stdin", io.StringIO(""))  # not a TTY, no flag: refuse rather than hang or guess
    with pytest.raises(SystemExit, match="non-interactive"):
        cli.main(["create-user", name + "x"])
    assert cli.main(["create-user", name, "--generate"]) == 1  # duplicate


def test_cli_bootstrap_creates_once_from_a_hash(cli_env, capsys, anon_client):
    name = "boot." + uuid.uuid4().hex[:6]
    cli_env.setenv("NEXORA_BOOTSTRAP_USERNAME", name)
    cli_env.setenv("NEXORA_BOOTSTRAP_PASSWORD_HASH", passwords.hash_password("bootstrap-password-1"))
    get_settings.cache_clear()
    assert cli.main(["bootstrap"]) == 0
    assert cli.main(["bootstrap"]) == 0
    out = capsys.readouterr().out
    assert "user created" in out and "already exists" in out
    login(anon_client, name, "bootstrap-password-1")
    cli_env.setenv("NEXORA_BOOTSTRAP_PASSWORD_HASH", "plaintext-is-refused")
    cli_env.setenv("NEXORA_BOOTSTRAP_USERNAME", name + "z")
    get_settings.cache_clear()
    assert cli.main(["bootstrap"]) == 1


def test_api_startup_bootstraps_the_operator_account_once(db_url, caplog):
    name = "start." + uuid.uuid4().hex[:6]
    settings = Settings(
        database_url=db_url,
        bootstrap_username=name,
        bootstrap_password_hash=passwords.hash_password("startup-password-1"),
    )
    with caplog.at_level(logging.INFO, logger="nexora.api"):
        with _client(settings) as c:
            login(c, name, "startup-password-1")
        with _client(settings):
            pass
    assert "bootstrap: created" in caplog.text and "bootstrap: exists" in caplog.text
    assert "startup-password-1" not in caplog.text and "$argon2id$" not in caplog.text
