"""Atomic CSV import and its optional durable asynchronous entry point."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from nexora.application import ingest_service, queries
from nexora.application.errors import AppError, Conflict, Invalid, NotFound
from nexora.domain.ids import canonical_json, sha256_hex
from nexora.ingest.csv_adapter import CsvSchemaError, read_csv_rows
from nexora.persistence import orm
from nexora.persistence.db import session_scope
from nexora.settings import get_settings


@dataclass(frozen=True)
class CsvPayload:
    content: bytes
    name: str
    boundary: list[str]
    file_sha256: str
    payload_sha256: str
    key: str

    @classmethod
    def prepare(cls, content: bytes, name: str, boundary_field: str, key: str | None) -> CsvPayload:
        boundary = sorted({part.strip() for part in boundary_field.replace("\n", ",").split(",") if part.strip()})
        file_sha = sha256_hex(content)
        digest = sha256_hex(canonical_json([file_sha, name, boundary]))
        return cls(content, name, boundary, file_sha, digest, f"explicit:{key}" if key else f"automatic:{digest}")


def persist_csv(session: Session, payload: CsvPayload, *, scope: str, max_rows: int) -> dict[str, Any]:
    request, claimed = ingest_service.reserve_csv_import(
        session,
        scope=scope,
        key=payload.key,
        payload_sha256=payload.payload_sha256,
    )
    if not claimed:
        assert request.result is not None
        return request.result
    try:
        rows, _ = read_csv_rows(payload.content, max_rows=max_rows)
    except CsvSchemaError as exc:
        raise Invalid(exc.code, str(exc)) from exc
    timestamped = [bool(row.get("occurred_at") and str(row["occurred_at"]).strip()) for _, row in rows]
    precision = "mixed" if any(timestamped) and not all(timestamped) else ("timestamp" if any(timestamped) else "day")
    dataset = ingest_service.create_dataset(
        session,
        name=payload.name,
        source_kind="csv",
        time_precision=precision,
        coverage_contract={
            "source": "csv",
            "boundary_account_ids": payload.boundary,
            "upstream_observed": None,
            "declared_complete": False,
        },
        authorized_use_note="Uploaded by operator; operator is responsible for authorised use.",
        manifest_sha256=payload.file_sha256,
    )
    batch, report = ingest_service.ingest_rows(
        session,
        dataset=dataset,
        rows=rows,
        source_id=f"csv:{payload.file_sha256[:16]}",
        content_sha256=payload.file_sha256,
        file_name=None,
        is_synthetic=False,
        fresh_dataset=True,
    )
    summary = queries.dataset_dict(session, dataset)
    summary["created_at"] = dataset.created_at.isoformat()
    outcome = {"dataset": summary, "batch_id": str(batch.id), "report": report.as_dict()}
    request.result = outcome
    return outcome


def enqueue_csv(session: Session, payload: CsvPayload, *, scope: str, max_rows: int) -> orm.CsvImportJob:
    stmt = (
        insert(orm.CsvImportJob)
        .values(
            id=uuid.uuid4(),
            scope=scope,
            tenant=session.info.get("tenant"),
            request_key=payload.key,
            payload_sha256=payload.payload_sha256,
            file_sha256=payload.file_sha256,
            content=payload.content,
            name=payload.name,
            boundary=payload.boundary,
            max_rows=max_rows,
            status="accepted",
        )
        .on_conflict_do_nothing(constraint="uq_csv_import_job_request")
        .returning(orm.CsvImportJob)
    )
    job = session.scalar(stmt)
    if job is None:
        job = session.scalars(
            select(orm.CsvImportJob).where(
                orm.CsvImportJob.scope == scope,
                orm.CsvImportJob.request_key == payload.key,
            )
        ).one()
    if job.payload_sha256 != payload.payload_sha256:
        raise Conflict("IMPORT_IDEMPOTENCY_CONFLICT", "idempotency key belongs to another import payload")
    return job


def get_csv_job(session: Session, job_id: uuid.UUID, scope: str) -> orm.CsvImportJob:
    job = session.scalar(select(orm.CsvImportJob).where(orm.CsvImportJob.id == job_id, orm.CsvImportJob.scope == scope))
    if job is None:
        raise NotFound("IMPORT_JOB_NOT_FOUND", "CSV import job does not exist")
    return job


def cancel_csv_job(session: Session, job_id: uuid.UUID, scope: str) -> orm.CsvImportJob:
    job = get_csv_job(session, job_id, scope)
    if job.status == "cancelled":
        return job
    if job.status != "accepted":
        raise Conflict("IMPORT_ALREADY_STARTED", "only an accepted import can be cancelled")
    statement = text("""
        UPDATE csv_import_jobs SET status='cancelled', content=NULL
        WHERE id IN (
            SELECT id FROM csv_import_jobs WHERE id=:job_id AND status='accepted' FOR UPDATE SKIP LOCKED
        )
        RETURNING id
    """)
    if session.execute(statement, {"job_id": job.id}).scalar_one_or_none() is None:
        raise Conflict("IMPORT_ALREADY_STARTED", "only an accepted import can be cancelled")
    session.refresh(job)
    return job


_CLAIMABLE = "(status = 'accepted' OR (status = 'processing' AND lease_until <= now()))"
REAP = text(f"""
    UPDATE csv_import_jobs SET status='failed', lease_until=NULL, content=NULL, error_code='ATTEMPTS_EXHAUSTED'
    WHERE id IN (
        SELECT id FROM csv_import_jobs WHERE {_CLAIMABLE} AND attempt_count >= :max_attempts
        FOR UPDATE SKIP LOCKED LIMIT 100
    )
""")
CLAIM = text(f"""
    UPDATE csv_import_jobs SET status='processing', attempt_count=attempt_count+1,
        lease_until=now()+make_interval(secs=>:lease)
    WHERE id = (
        SELECT id FROM csv_import_jobs WHERE {_CLAIMABLE} AND attempt_count < :max_attempts
        ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1
    )
    RETURNING id,attempt_count
""")


def run_import_once(factory: sessionmaker[Session]) -> uuid.UUID | None:
    settings = get_settings()
    with session_scope(factory) as session:
        session.execute(REAP, {"max_attempts": settings.job_max_attempts})
        claim = session.execute(
            CLAIM,
            {
                "max_attempts": settings.job_max_attempts,
                "lease": settings.job_lease_seconds,
            },
        ).first()
    if claim is None:
        return None
    job_id, attempt = claim
    with session_scope(factory) as session:
        job = session.scalar(
            select(orm.CsvImportJob)
            .where(
                orm.CsvImportJob.id == job_id,
                orm.CsvImportJob.status == "processing",
                orm.CsvImportJob.attempt_count == attempt,
                orm.CsvImportJob.lease_until > text("now()"),
            )
            .with_for_update()
        )
        if job is None:
            return job_id
        assert job.content is not None
        session.info.update(tenant=job.tenant, demo_scope=job.tenant is None)
        payload = CsvPayload(job.content, job.name, job.boundary, job.file_sha256, job.payload_sha256, job.request_key)
        try:
            with session.begin_nested():
                job.result = persist_csv(session, payload, scope=job.scope, max_rows=job.max_rows)
        except AppError as exc:
            job.status = "failed"
            job.error_code = exc.code
        else:
            job.status = "completed"
        job.content = None
        job.lease_until = None
    return job_id
