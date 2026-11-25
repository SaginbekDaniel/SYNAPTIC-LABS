"""Stepwise upgrade along the deployed path: 0002 → 0003 (production) → 0004 (head), then no ORM drift.

Runs in a throwaway PostgreSQL schema of the disposable test database (``search_path`` points at it), so the
schema the rest of the suite uses is never touched.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text

from nexora.persistence.orm import Base

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def probe(db_url: str) -> Iterator[tuple[Config, Engine]]:
    schema = f"migration_probe_{uuid.uuid4().hex[:12]}"
    admin = create_engine(db_url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(db_url, connect_args={"options": f"-csearch_path={schema}"})
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    # env.py requires a URL even though _upgrade() hands it a connection; "%%" survives ConfigParser interpolation.
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%"))
    try:
        yield cfg, engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _upgrade(cfg: Config, engine: Engine, target: str) -> None:
    # env.py opens its connection from the URL, which cannot carry search_path; hand it ours instead.
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, target)


def _version(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_production_path_upgrades_stepwise_and_matches_the_orm(probe: tuple[Config, Engine]) -> None:
    cfg, engine = probe
    _upgrade(cfg, engine, "0002")
    assert _version(engine) == "0002"
    assert "users" not in _tables(engine)

    _upgrade(cfg, engine, "0003")  # where the deployment record says production is
    assert _version(engine) == "0003"
    tables = _tables(engine)
    assert {"users", "auth_sessions", "login_attempts"} <= tables
    assert "hypothesis_assessments" not in tables
    with engine.begin() as conn:  # an account created while production sits at 0003 must survive 0004
        conn.execute(
            text(
                "INSERT INTO users (id, username, display_name, password_hash) "
                "VALUES (:id, 'prod-analyst', 'Prod Analyst', 'x')"
            ),
            {"id": uuid.uuid4()},
        )

    _upgrade(cfg, engine, "head")
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head == "0004" or (head is not None and head > "0004")
    assert _version(engine) == head
    assert "hypothesis_assessments" in _tables(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users WHERE username = 'prod-analyst'")).scalar_one() == 1
        # 0005 (B-011): an account from before roles keeps its permissions, i.e. becomes an analyst.
        assert conn.execute(text("SELECT role FROM users WHERE username = 'prod-analyst'")).scalar_one() == "analyst"
        # `alembic check` equivalent: the stepwise result is exactly what the ORM declares.
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
