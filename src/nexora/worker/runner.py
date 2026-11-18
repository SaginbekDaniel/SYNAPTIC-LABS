"""Lease-based PostgreSQL job worker (spec §16.3).

Semantics: at-least-once processing with idempotent effects — not exactly-once.

1. Claim one job in a short transaction with ``FOR UPDATE SKIP LOCKED``.
2. Compute outside any row lock while a heartbeat thread extends the lease.
3. Publish in one transaction after re-checking that this worker still owns the lease.
4. On failure: bounded retries, then terminal ``failed`` with a visible error code.
Expired leases (crashed worker) become claimable again.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
import traceback
import uuid
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

from nexora.analytics.config import AnalysisConfig, default_config
from nexora.application import analysis_service
from nexora.persistence import orm
from nexora.persistence.db import session_factory, session_scope
from nexora.settings import get_settings

log = logging.getLogger("nexora.worker")

CLAIM_SQL = text(
    """
    UPDATE analysis_jobs SET status = 'running', lease_owner = :owner,
        lease_until = now() + make_interval(secs => :lease), attempt_count = attempt_count + 1,
        updated_at = now()
    WHERE id = (
        SELECT id FROM analysis_jobs
        WHERE (status = 'queued') OR (status = 'running' AND lease_until < now())
        ORDER BY created_at, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, dataset_id, max_ingest_seq, attempt_count
    """
)


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class _Heartbeat:
    def __init__(self, factory: sessionmaker[Session], job_id: uuid.UUID, owner: str, lease: int) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(factory, job_id, owner, lease), daemon=True)

    def _run(self, factory: sessionmaker[Session], job_id: uuid.UUID, owner: str, lease: int) -> None:
        while not self._stop.wait(max(1.0, lease / 3)):
            try:
                with session_scope(factory) as s:
                    s.execute(
                        text(
                            "UPDATE analysis_jobs SET lease_until = now() + make_interval(secs => :lease), "
                            "updated_at = now() "
                            "WHERE id = :id AND lease_owner = :owner AND status = 'running'"
                        ),
                        {"lease": lease, "id": job_id, "owner": owner},
                    )
            except Exception:  # heartbeat failure must not crash computation; lease expiry handles it
                log.exception("heartbeat failed for job %s", job_id)

    def __enter__(self) -> _Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


def run_once(
    factory: sessionmaker[Session], *, owner: str | None = None, config: AnalysisConfig | None = None
) -> uuid.UUID | None:
    """Claim and process at most one job. Returns the job id, or ``None`` if the queue is empty."""
    settings = get_settings()
    cfg = config or default_config()
    owner = owner or worker_identity()
    with session_scope(factory) as s:
        claimed = s.execute(CLAIM_SQL, {"owner": owner, "lease": settings.job_lease_seconds}).first()
    if claimed is None:
        return None
    job_id, dataset_id, max_seq, attempts = claimed
    log.info("claimed job %s (attempt %s) for dataset %s", job_id, attempts, dataset_id)
    try:
        with _Heartbeat(factory, job_id, owner, settings.job_lease_seconds):
            with session_scope(factory) as s:
                transfers, contract = analysis_service.load_inputs(s, dataset_id, max_seq)
            output = analysis_service.compute(dataset_id, transfers, contract, cfg)
            with session_scope(factory) as s:
                job = s.execute(
                    select(orm.AnalysisJob).where(orm.AnalysisJob.id == job_id).with_for_update()
                ).scalar_one()
                if job.lease_owner != owner or job.status != "running":
                    log.warning("lost lease on job %s; result discarded (another worker owns it)", job_id)
                    return job_id
                snapshot_id = analysis_service.publish(
                    s, dataset_id=dataset_id, max_ingest_seq=max_seq, out=output, config=cfg
                )
                job.status = "succeeded"
                job.snapshot_id = snapshot_id
                job.lease_owner = None
                job.lease_until = None
                job.error_code = None
                job.error_summary = None
                s.execute(update(orm.AnalysisJob).where(orm.AnalysisJob.id == job_id).values(updated_at=text("now()")))
        log.info("job %s published snapshot %s", job_id, snapshot_id)
    except Exception as exc:
        log.error("job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
        with session_scope(factory) as s:
            terminal = attempts >= settings.job_max_attempts
            s.execute(
                update(orm.AnalysisJob)
                .where(orm.AnalysisJob.id == job_id, orm.AnalysisJob.lease_owner == owner)
                .values(
                    status="failed" if terminal else "queued",
                    lease_owner=None,
                    lease_until=None,
                    error_code=getattr(exc, "code", "ANALYSIS_FAILED"),
                    error_summary=str(exc)[:500],
                    updated_at=text("now()"),
                )
            )
    return job_id


def drain(factory: sessionmaker[Session], *, config: AnalysisConfig | None = None, max_jobs: int = 100) -> int:
    count = 0
    while count < max_jobs and run_once(factory, config=config) is not None:
        count += 1
    return count


def install_stop_signals(stop: threading.Event) -> None:
    """Translate SIGTERM/SIGINT into a cooperative stop.

    Platforms (Docker, Railway) send SIGTERM before SIGKILL on redeploy. The loop finishes the job it
    is computing and exits instead of abandoning it; a job interrupted by SIGKILL is still recovered
    when its lease expires.
    """

    def _request_stop(signum: int, _frame: Any) -> None:
        log.info("received signal %s; finishing the current job, then stopping", signum)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _request_stop)


def serve(
    factory: sessionmaker[Session],
    *,
    owner: str,
    stop: threading.Event,
    poll: float,
    config: AnalysisConfig | None = None,
) -> int:
    """Process jobs until ``stop`` is set. Returns the number of jobs processed."""
    processed = 0
    while not stop.is_set():
        try:
            if run_once(factory, owner=owner, config=config) is None:
                stop.wait(poll)
            else:
                processed += 1
        except Exception:
            log.exception("worker loop error; backing off")
            stop.wait(poll * 5)
    log.info("worker %s stopped after %s jobs", owner, processed)
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXORA analysis worker")
    parser.add_argument("--once", action="store_true", help="process queued jobs then exit")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )
    factory = session_factory()
    owner = worker_identity()
    log.info("worker %s started", owner)
    if args.once:
        log.info("processed %s jobs", drain(factory))
        return
    stop = threading.Event()
    install_stop_signals(stop)
    serve(factory, owner=owner, stop=stop, poll=get_settings().worker_poll_seconds)


if __name__ == "__main__":
    main()
