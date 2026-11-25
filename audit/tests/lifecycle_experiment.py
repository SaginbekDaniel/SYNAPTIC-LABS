"""Reversible failure and restart checks for a PostgreSQL cluster owned by this run."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import psycopg
from psycopg.errors import CheckViolation, ForeignKeyViolation
from test_audit import CSV_BYTES

PYTHON = sys.executable
STALL_WORKER = """
import time
from nexora.application import analysis_service
from nexora.worker import runner
def wait_in_compute(*args, **kwargs):
    print("AUDIT_WORKER_PAUSED", flush=True)
    time.sleep(60)
analysis_service.compute = wait_in_compute
runner.main()
"""


def retry(operation, predicate, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            value = operation()
            if predicate(value):
                return value
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for the expected local service state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--pg-ctl", required=True, type=Path)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--api-port", type=int, default=18102)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    postgres_data = scratch / "pgdata"
    assert scratch.name.startswith("nexora-audit.") and scratch.parent.resolve() == Path("/private/tmp").resolve()
    assert (postgres_data / "PG_VERSION").is_file()
    db = urlparse(args.dsn)
    assert db.hostname == "127.0.0.1" and db.port and db.path.endswith("_audit_migrate")
    assert (scratch / "pgsocket").is_dir()
    env = {
        **os.environ,
        "NEXORA_DATABASE_URL": args.dsn.replace("postgresql://", "postgresql+psycopg://", 1),
        "NEXORA_WORKER_POLL_SECONDS": "0.15",
        "NEXORA_JOB_LEASE_SECONDS": "2",
    }
    out = args.output.resolve().parent
    watch = []
    processes = []
    postgres_stopped = False

    def spawn(name, *command):
        with (out / f"lifecycle-{name}.log").open("w") as log:
            child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        processes.append(child)
        return child

    def start_api(name):
        return spawn(
            name, PYTHON, "-m", "uvicorn", "nexora.api.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)
        )

    def migrate(version):
        subprocess.run([PYTHON, "-m", "alembic", "upgrade", version], env=env, check=True)

    def pg_control(action):
        command = [str(args.pg_ctl), "-D", str(postgres_data), "-w"]
        if action == "stop":
            command += ["-m", "fast", "stop"]
        else:
            command += [
                "-l",
                str(scratch / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {db.port} -k {scratch / 'pgsocket'}",
                "start",
            ]
        subprocess.run(command, check=True)

    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{args.api_port}", timeout=5, trust_env=False) as api:
            server = start_api("api-before")
            get = api.get
            ready = "/health/ready"
            live = retry(lambda: get("/health/live"), lambda r: r.status_code == 200)
            before = get(ready)
            watch.append(
                {
                    "case": "no_migrations",
                    "live": live.status_code,
                    "ready": before.status_code,
                    "observed": before.json(),
                    "expected_ready": 503,
                }
            )
            migrate("0001")
            previous = get(ready)
            watch.append(
                {
                    "case": "outdated_migration",
                    "ready": previous.status_code,
                    "observed": previous.json(),
                    "expected_ready": 503,
                }
            )
            migrate("head")
            upgraded = get(ready)
            watch.append(
                {
                    "case": "migrated_to_head",
                    "ready": upgraded.status_code,
                    "observed": upgraded.json(),
                    "expected_ready": 200,
                }
            )

            imported = api.post(
                "/api/v1/datasets/import",
                data={"name": "audit recovery fixture"},
                files={"file": ("records.csv", CSV_BYTES, "text/csv")},
            )
            assert imported.status_code == 201
            dataset = imported.json()["dataset"]["id"]
            payload = {"dataset_id": dataset, "idempotency_key": f"audit-recovery-{uuid4()}"}
            created = api.post("/api/v1/analysis/jobs", json=payload)
            assert created.status_code == 202
            job_url = created.headers["location"]

            for attempt in (1, 2, 3):
                interrupted = spawn(f"worker-interrupted-{attempt}", PYTHON, "-c", STALL_WORKER)
                stalled_log = out / f"lifecycle-worker-interrupted-{attempt}.log"
                retry(stalled_log.read_text, lambda value: "AUDIT_WORKER_PAUSED" in value)
                interrupted.kill()
                interrupted.wait(timeout=5)
                state = get(job_url).json()
                assert state["status"] == "running" and state["attempt_count"] == attempt
            spawn("worker-recovery", PYTHON, "-m", "nexora.worker.runner")
            complete = retry(lambda: get(job_url).json(), lambda r: r["status"] == "succeeded")
            assert complete["snapshot_id"]
            watch.append(
                {
                    "case": "worker_hard_stop_three_times",
                    "final_status": complete["status"],
                    "attempt_count": complete["attempt_count"],
                    "configured_max": 3,
                    "expected_terminal_after_max": "failed",
                }
            )

            db_checks = {}
            for name, bad_column, value, failure in (
                ("positive_amount", "amount_minor", 0, CheckViolation),
                ("dataset_foreign_key", "dataset_id", uuid4(), ForeignKeyViolation),
            ):
                try:
                    with psycopg.connect(args.dsn) as conn:
                        query = psycopg.sql.SQL("UPDATE transactions SET {} = %s WHERE dataset_id = %s").format(
                            psycopg.sql.Identifier(bad_column)
                        )
                        conn.execute(query, (value, dataset))
                        conn.rollback()
                except failure as exc:
                    db_checks[name] = exc.sqlstate
                else:
                    db_checks[name] = "constraint did not reject the synthetic row"
            watch.append({"case": "database_constraints_rollback", "observed": db_checks})

            pg_control("stop")
            postgres_stopped = True
            offline = get(ready)
            data_offline = get(f"/api/v1/datasets/{dataset}")
            watch.append(
                {
                    "case": "database_outage",
                    "live": get("/health/live").status_code,
                    "ready": offline.status_code,
                    "data": data_offline.status_code,
                    "data_error": data_offline.json().get("error", {}).get("code"),
                }
            )
            pg_control("start")
            postgres_stopped = False
            retry(lambda: get(ready), lambda r: r.status_code == 200)
            server.terminate()
            server.wait(timeout=10)
            start_api("api-after")
            retry(lambda: get(ready), lambda r: r.status_code == 200)
            surviving = get(f"/api/v1/datasets/{dataset}").json()
            repeat = api.post("/api/v1/analysis/jobs", json=payload).json()
            with psycopg.connect(args.dsn) as conn:
                count = conn.execute(
                    "SELECT count(*) FROM graph_snapshots WHERE dataset_id = %s", (dataset,)
                ).fetchone()[0]
            watch.append(
                {
                    "case": "postgres_and_api_restart",
                    "ready": get(ready).status_code,
                    "saved_transactions": surviving["transactions_count"],
                    "same_job": complete["id"] == repeat["id"],
                    "published_snapshot_count": count,
                }
            )
    finally:
        if postgres_stopped:
            pg_control("start")
        for child in reversed(processes):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        args.output.write_text(json.dumps(watch, indent=2) + "\n")


if __name__ == "__main__":
    main()
