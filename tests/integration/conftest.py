from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from scripts import reset_disposable_db
from tests.auth_helpers import BASE_URL, ensure_user, login

TEST_URL = os.environ.get("NEXORA_TEST_DATABASE_URL", "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_test")


def _db_available() -> bool:
    try:
        with create_engine(TEST_URL).connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_url() -> str:
    if not _db_available():
        pytest.skip(f"PostgreSQL not reachable at {TEST_URL}")
    # Every run starts from an empty, freshly migrated schema. Downgrades are not used for this:
    # they refuse to discard published analyses (migration 0002).
    reset_disposable_db.reset(TEST_URL)
    return TEST_URL


@pytest.fixture(scope="session")
def factory(db_url: str):
    return sessionmaker(bind=create_engine(db_url), expire_on_commit=False)


@pytest.fixture()
def settings(db_url: str):
    from nexora.settings import Settings

    # Every TestClient request comes from the same address, so the per-client sign-in failure budget
    # would be shared by the whole suite; test_auth.py exercises that limit with its own settings.
    return Settings(database_url=db_url, login_max_failures_per_client=10_000)


@pytest.fixture()
def anon_client(settings):
    from fastapi.testclient import TestClient

    from nexora.api.main import create_app

    with TestClient(create_app(settings), base_url=BASE_URL) as c:
        yield c


@pytest.fixture()
def client(settings, factory):
    """An API client signed in as the test analyst."""
    from fastapi.testclient import TestClient

    from nexora.api.main import create_app

    ensure_user(factory)
    with TestClient(create_app(settings), base_url=BASE_URL) as c:
        login(c)
        yield c
