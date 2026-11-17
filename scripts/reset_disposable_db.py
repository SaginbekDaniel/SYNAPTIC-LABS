"""Drop and re-create the schema of a *disposable* database, then migrate to head.

Used by integration tests and the browser E2E stack. Migration downgrades are not a reset
mechanism: they refuse to discard published analyses (see migration 0002).

    NEXORA_DATABASE_URL=... uv run python scripts/reset_disposable_db.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
DISPOSABLE_SUFFIXES = ("_test", "_e2e")


def reset(url: str) -> None:
    name = make_url(url).database or ""
    if not name.endswith(DISPOSABLE_SUFFIXES):
        raise SystemExit(f"refusing to reset {name!r}: database name must end with {DISPOSABLE_SUFFIXES}")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    reset(sys.argv[1] if len(sys.argv) > 1 else os.environ["NEXORA_DATABASE_URL"])
