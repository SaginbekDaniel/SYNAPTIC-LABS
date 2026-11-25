"""Record SQL statement counts for neighborhoods and alerts in an audit database."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import make_url

from nexora.api.main import create_app
from nexora.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    database = make_url(args.dsn)
    assert database.host in {"localhost", "127.0.0.1"} and (database.database or "").endswith("_audit_perf")
    app = create_app(Settings(database_url=args.dsn, _env_file=None))
    engine = app.state.session_factory.kw["bind"]
    with engine.connect() as conn:
        targets = conn.execute(
            text("SELECT d.name, d.id, s.id FROM datasets d JOIN graph_snapshots s ON s.dataset_id = d.id")
        ).all()

    started, samples = {}, []

    @event.listens_for(engine, "before_cursor_execute")
    def before(_, cursor, *_args):
        started[id(cursor)] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after(_, cursor, *_args):
        samples.append((time.perf_counter() - started.pop(id(cursor))) * 1000)

    report = []
    with TestClient(app) as client:
        for name, dataset, snapshot in targets:
            neighborhood = f"/api/v1/snapshots/{snapshot}/neighborhood"
            for label, path, params in (
                ("depth_1", neighborhood, {"account_id": "hub", "depth": 1}),
                ("depth_2", neighborhood, {"account_id": "hub", "depth": 2}),
                ("alerts", "/api/v1/alerts", {"dataset_id": str(dataset), "limit": 50}),
            ):
                started.clear()
                samples.clear()
                response = client.get(path, params=params)
                assert response.status_code == 200
                body = response.json()
                report.append(
                    {
                        "dataset": name,
                        "route": label,
                        "sql_statements": len(samples),
                        "sql_wall_ms": sum(samples),
                        "result_size": len(body["nodes"] if "nodes" in body else body["items"]),
                    }
                )
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
