"""Connectivity and migration compatibility checks for the running release."""

from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from nexora.persistence.orm import AnalysisJob

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def release_heads() -> tuple[str, ...]:
    return tuple(sorted(ScriptDirectory(str(MIGRATIONS)).get_heads()))


def database_readiness(factory: sessionmaker[Session], expected: tuple[str, ...]) -> dict:
    result: dict = {
        "database": False,
        "schema": "unavailable",
        "migration": None,
        "expected_migrations": list(expected),
        "queue": {},
    }
    try:
        with factory() as session:
            session.execute(text("SELECT 1"))
            result.update(database=True, schema="incompatible")
            connection = session.connection()
            if not inspect(connection).has_table("alembic_version"):
                result["schema"] = "missing"
                return result
            actual = tuple(sorted(MigrationContext.configure(connection).get_current_heads()))
            result["migration"] = ",".join(actual) if actual else None
            if not actual:
                result["schema"] = "missing"
            elif actual == expected:
                queue = session.execute(select(AnalysisJob.status, func.count()).group_by(AnalysisJob.status))
                result.update(schema="compatible", queue={status: count for status, count in queue})
    except SQLAlchemyError:
        pass  # The check reports state without exposing driver or connection details.
    return result
