from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.downgrade(cfg, "base")  # every run starts from an empty, freshly migrated schema
    command.upgrade(cfg, "head")
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
