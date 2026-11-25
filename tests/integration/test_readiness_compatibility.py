from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from nexora.api.main import create_app
from nexora.persistence.health import release_heads


def test_readiness_distinguishes_missing_outdated_unknown_and_current_schema(db_url, settings):
    schema = f"health_{uuid4().hex}"
    server = create_engine(db_url)
    with server.begin() as conn:
        conn.execute(CreateSchema(schema))
    scoped = make_url(db_url).update_query_dict({"options": f"-csearch_path={schema}"})
    url = scoped.render_as_string(hide_password=False)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    engine = create_engine(scoped)
    try:
        with TestClient(create_app(settings.model_copy(update={"database_url": url}))) as client:
            missing = client.get("/health/ready")
            assert missing.status_code == 503
            assert missing.json()["database"] and missing.json()["schema"] == "missing"
            assert client.get("/health/live").status_code == 200

            command.upgrade(cfg, "0002")
            old = client.get("/health/ready")
            assert old.status_code == 503
            assert old.json()["database"] and old.json()["schema"] == "incompatible"
            assert old.json()["migration"] == "0002"

            command.upgrade(cfg, "head")
            head = client.get("/health/ready")
            assert head.status_code == 200
            assert head.json()["schema"] == "compatible"
            assert head.json()["expected_migrations"] == list(release_heads())

            with engine.begin() as conn:
                conn.execute(text("UPDATE alembic_version SET version_num = 'foreign_revision'"))
            unknown = client.get("/health/ready")
            assert unknown.status_code == 503
            assert unknown.json()["schema"] == "incompatible"
    finally:
        engine.dispose()
        with server.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        server.dispose()
