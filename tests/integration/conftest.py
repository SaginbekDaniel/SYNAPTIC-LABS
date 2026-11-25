from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from scripts import reset_disposable_db

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

    return Settings(database_url=db_url)


@pytest.fixture()
def client(settings):
    from fastapi.testclient import TestClient

    from nexora.api.main import create_app

    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture()
def isolated_schema(db_url):
    """Give migration checks a private schema inside the disposable test database."""
    schema = f"migration_{uuid4().hex}"
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(CreateSchema(schema))
    try:
        yield (
            make_url(db_url)
            .update_query_dict({"options": f"-csearch_path={schema}"})
            .render_as_string(hide_password=False)
        )
    finally:
        with engine.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        engine.dispose()
