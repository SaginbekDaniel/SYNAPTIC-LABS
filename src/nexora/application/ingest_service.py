"""Ingestion: canonical validation, database-enforced deduplication, import reports."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nexora.domain.ids import transaction_uuid
from nexora.evaluation.generator import generate
from nexora.ingest.validation import CanonicalRecord, ImportReport, RowIssue, prepare_batch
from nexora.persistence import orm

CHUNK = 1000


def create_dataset(
    session: Session,
    *,
    name: str,
    source_kind: str,
    time_precision: str,
    coverage_contract: dict[str, Any],
    description: str | None = None,
    authorized_use_note: str | None = None,
    manifest_sha256: str | None = None,
) -> orm.Dataset:
    ds = orm.Dataset(
        id=uuid.uuid4(),
        name=name,
        source_kind=source_kind,
        description=description,
        time_precision=time_precision,
        coverage_contract=coverage_contract,
        authorized_use_note=authorized_use_note,
        raw_manifest_sha256=manifest_sha256,
    )
    session.add(ds)
    session.flush()
    return ds


def _row_values(dataset_id: uuid.UUID, batch_id: uuid.UUID, r: CanonicalRecord) -> dict[str, Any]:
    return {
        "id": uuid.UUID(transaction_uuid(str(dataset_id), r.source_id, r.source_transaction_id)),
        "dataset_id": dataset_id,
        "import_batch_id": batch_id,
        "source_id": r.source_id,
        "source_transaction_id": r.source_transaction_id,
        "sender_account_id": r.sender_account_id,
        "receiver_account_id": r.receiver_account_id,
        "amount_minor": r.amount_minor,
        "currency": r.currency,
        "occurred_at": r.occurred_at,
        "observed_date": r.observed_date,
        "time_precision": r.time_precision,
        "status": r.status,
        "is_synthetic": r.is_synthetic,
        "raw_record_hash": r.content_hash(),
    }


def ingest_rows(
    session: Session,
    *,
    dataset: orm.Dataset,
    rows: Sequence[tuple[int, Mapping[str, object]]],
    source_id: str,
    content_sha256: str,
    file_name: str | None,
    is_synthetic: bool,
) -> tuple[orm.ImportBatch, ImportReport]:
    records, report = prepare_batch(rows, source_id=source_id, is_synthetic=is_synthetic)
    report.content_sha256 = content_sha256
    batch = orm.ImportBatch(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        file_name=file_name,
        content_sha256=content_sha256,
        accepted=0,
        duplicate=0,
        quarantined=0,
        rejected=0,
        report={},
        status="running",
    )
    session.add(batch)
    session.flush()

    accepted = 0
    for start in range(0, len(records), CHUNK):
        chunk = records[start : start + CHUNK]
        keys = [(r.source_id, r.source_transaction_id) for r in chunk]
        existing = {
            (sid, stid): h
            for sid, stid, h in session.execute(
                select(
                    orm.Transaction.source_id,
                    orm.Transaction.source_transaction_id,
                    orm.Transaction.raw_record_hash,
                ).where(
                    orm.Transaction.dataset_id == dataset.id,
                    tuple_(orm.Transaction.source_id, orm.Transaction.source_transaction_id).in_(keys),
                )
            )
        }
        fresh: list[CanonicalRecord] = []
        for r in chunk:
            prior = existing.get((r.source_id, r.source_transaction_id))
            if prior is None:
                fresh.append(r)
            elif prior == r.content_hash():
                report.duplicated_identical += 1
            else:
                report.quarantine(
                    RowIssue(
                        0,
                        "CONFLICTING_TRANSACTION_DUPLICATE",
                        "source_transaction_id",
                        "transaction id already stored with different content",
                    )
                )
        if not fresh:
            continue
        stmt = (
            insert(orm.Transaction)
            .values([_row_values(dataset.id, batch.id, r) for r in fresh])
            .on_conflict_do_nothing(constraint="uq_transactions_source")
            .returning(orm.Transaction.source_transaction_id)
        )
        inserted = {row[0] for row in session.execute(stmt)}
        accepted += len(inserted)
        # Rows lost to a concurrent import of the same key are re-classified, never double counted.
        for r in fresh:
            if r.source_transaction_id not in inserted:
                stored = session.execute(
                    select(orm.Transaction.raw_record_hash).where(
                        orm.Transaction.dataset_id == dataset.id,
                        orm.Transaction.source_id == r.source_id,
                        orm.Transaction.source_transaction_id == r.source_transaction_id,
                    )
                ).scalar_one()
                if stored == r.content_hash():
                    report.duplicated_identical += 1
                else:
                    report.quarantine(
                        RowIssue(
                            0,
                            "CONFLICTING_TRANSACTION_DUPLICATE",
                            "source_transaction_id",
                            "transaction id already stored with different content",
                        )
                    )
    report.accepted = accepted
    batch.accepted = accepted
    batch.duplicate = report.duplicated_identical
    batch.quarantined = report.quarantined
    batch.rejected = report.rejected
    batch.report = report.as_dict()
    batch.status = "completed"
    batch.completed_at = dt.datetime.now(dt.UTC)
    session.flush()
    return batch, report


def create_synthetic_dataset(
    session: Session, *, suite: str, seed: int, precision: str = "day"
) -> tuple[orm.Dataset, orm.ImportBatch, ImportReport]:
    """Generate a labelled synthetic suite and ingest only its *source rows*.

    Ground truth stays in the generator output and is never persisted here (ADR-009).
    """
    generated = generate(suite, seed, precision=precision)  # type: ignore[arg-type]
    ds = create_dataset(
        session,
        name=f"{suite} · seed {seed}",
        source_kind="synthetic",
        time_precision=precision,
        coverage_contract=generated.coverage_contract,
        description=f"SYNTHETIC dataset generated by {generated.coverage_contract['generator_version']}",
        authorized_use_note="Synthetic data generated locally; contains no real customer information.",
        manifest_sha256=generated.manifest_sha256,
    )
    rows = list(enumerate(generated.rows, start=1))
    batch, report = ingest_rows(
        session,
        dataset=ds,
        rows=rows,
        source_id=f"synthetic:{suite}:{seed}",
        content_sha256=generated.manifest_sha256,
        file_name=None,
        is_synthetic=True,
    )
    return ds, batch, report
