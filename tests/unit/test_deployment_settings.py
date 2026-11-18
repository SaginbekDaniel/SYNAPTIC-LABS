"""Deployment-facing settings: hosted PostgreSQL URLs, worker shutdown."""

from __future__ import annotations

import threading

import pytest

from nexora.settings import Settings, normalize_database_url
from nexora.worker import runner


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # Railway / Heroku-style URLs name no driver; SQLAlchemy would pick the uninstalled psycopg2.
        (
            "postgresql://u:p@db.railway.internal:5432/railway",
            "postgresql+psycopg://u:p@db.railway.internal:5432/railway",
        ),
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("POSTGRESQL://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        # Already explicit: unchanged.
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        # Another driver or database is left alone so the misconfiguration surfaces at connect time.
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
        # Surrounding whitespace from copy-pasted variables is dropped.
        ("  postgresql://u:p@host/db\n", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_normalize_database_url(given: str, expected: str) -> None:
    assert normalize_database_url(given) == expected


def test_normalize_preserves_credentials_and_query_exactly() -> None:
    url = "postgresql://user:p%40ss%3Aw0rd@host:6543/db?sslmode=require&application_name=nexora"
    assert normalize_database_url(url) == (
        "postgresql+psycopg://user:p%40ss%3Aw0rd@host:6543/db?sslmode=require&application_name=nexora"
    )


def test_settings_normalize_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXORA_DATABASE_URL", "postgresql://u:p@db:5432/railway")
    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@db:5432/railway"  # type: ignore[call-arg]


def test_deployment_defaults_keep_local_development_open() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.expose_api_docs is True
    assert s.gateway_token == ""


def test_serve_stops_cooperatively_after_the_running_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stop request (SIGTERM) lets the in-flight job finish and claims nothing afterwards."""
    stop = threading.Event()
    calls: list[str] = []

    def fake_run_once(factory: object, *, owner: str, config: object = None) -> object:
        calls.append(owner)
        stop.set()  # the signal arrives while this job is being processed
        return "job-1"

    monkeypatch.setattr(runner, "run_once", fake_run_once)
    processed = runner.serve(object(), owner="w1", stop=stop, poll=0.01)  # type: ignore[arg-type]
    assert processed == 1
    assert calls == ["w1"]


def test_serve_survives_loop_errors_until_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    stop = threading.Event()
    attempts = 0

    def flaky(factory: object, *, owner: str, config: object = None) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("database restarting")
        stop.set()
        return None

    monkeypatch.setattr(runner, "run_once", flaky)
    assert runner.serve(object(), owner="w1", stop=stop, poll=0.001) == 0  # type: ignore[arg-type]
    assert attempts == 2
