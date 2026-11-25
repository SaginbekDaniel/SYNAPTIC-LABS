"""Analysis jobs and atomic, idempotent publication of snapshot outputs (spec §7.5, §16.3-16.4)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nexora.analytics import risk as risk_engine
from nexora.analytics.config import AnalysisConfig
from nexora.analytics.context import VerifiedContext
from nexora.analytics.pipeline import AnalysisOutput, run_analysis
from nexora.application.errors import Conflict, Invalid, NotFound
from nexora.domain.analysis import Formation, RiskAssessment
from nexora.domain.ids import canonical_json, sha256_hex
from nexora.domain.transfers import ObservedTransfer
from nexora.persistence import orm
from nexora.persistence.access import dataset_filter


def dataset_watermark(session: Session, dataset_id: uuid.UUID) -> int:
    return int(
        session.execute(
            select(func.coalesce(func.max(orm.Transaction.ingest_seq), 0)).where(
                orm.Transaction.dataset_id == dataset_id
            )
        ).scalar_one()
    )


def request_analysis(
    session: Session,
    *,
    dataset_id: uuid.UUID,
    requested_by: str,
    config: AnalysisConfig,
    idempotency_key: str | None = None,
    context: VerifiedContext | None = None,
) -> orm.AnalysisJob:
    if session.scalar(select(orm.Dataset.id).where(orm.Dataset.id == dataset_id, dataset_filter(session))) is None:
        raise NotFound("DATASET_NOT_FOUND", "dataset does not exist")
    watermark = dataset_watermark(session, dataset_id)
    if watermark == 0:
        raise Invalid("DATASET_EMPTY", "dataset has no transactions to analyse")
    configuration = {
        "detectors": config.detectors,
        "risk_policy": config.risk_policy,
        "config_sha256": config.config_sha256,
        "context": context.model_dump(mode="json") if context else None,
        "context_sha256": context.manifest() if context else None,
    }
    key = idempotency_key or f"analysis:{dataset_id}:{watermark}:{config.config_sha256}"
    if idempotency_key is None and configuration["context_sha256"] is not None:
        key += f":{configuration['context_sha256']}"
    if (tenant := session.info.get("tenant")) is not None:
        key = "tenant:" + sha256_hex(canonical_json([tenant, key]))
    stmt = (
        insert(orm.AnalysisJob)
        .values(
            id=uuid.uuid4(),
            dataset_id=dataset_id,
            kind="full_analysis",
            status="queued",
            idempotency_key=key,
            requested_by=requested_by,
            max_ingest_seq=watermark,
            analysis_configuration=configuration,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    session.execute(stmt)
    job = session.execute(select(orm.AnalysisJob).where(orm.AnalysisJob.idempotency_key == key)).scalar_one()
    if job.dataset_id != dataset_id:
        raise Invalid("IDEMPOTENCY_KEY_REUSED", "idempotency key belongs to another dataset")
    if job.analysis_configuration is not None and any(
        job.analysis_configuration.get(field) != configuration[field] for field in ("config_sha256", "context_sha256")
    ):
        raise Conflict("ANALYSIS_IDEMPOTENCY_CONFLICT", "idempotency key belongs to a different configuration")
    return job


def load_transfers(session: Session, dataset_id: uuid.UUID, max_ingest_seq: int) -> list[ObservedTransfer]:
    rows = session.execute(
        select(orm.Transaction)
        .where(orm.Transaction.dataset_id == dataset_id, orm.Transaction.ingest_seq <= max_ingest_seq)
        .order_by(orm.Transaction.ingest_seq)
    ).scalars()
    return [
        ObservedTransfer(
            transaction_id=str(t.id),
            source_transaction_id=t.source_transaction_id,
            sender=t.sender_account_id,
            receiver=t.receiver_account_id,
            amount_minor=int(t.amount_minor),
            currency=t.currency,
            observed_date=t.observed_date,
            occurred_at=t.occurred_at,
            precision=t.time_precision,  # type: ignore[arg-type]
            status=t.status,  # type: ignore[arg-type]
        )
        for t in rows
    ]


def load_inputs(
    session: Session, dataset_id: uuid.UUID, max_ingest_seq: int
) -> tuple[list[ObservedTransfer], dict[str, Any]]:
    dataset = session.get(orm.Dataset, dataset_id)
    if dataset is None:
        raise NotFound("DATASET_NOT_FOUND", "dataset does not exist")
    return load_transfers(session, dataset_id, max_ingest_seq), dict(dataset.coverage_contract)


def compute(
    dataset_id: uuid.UUID, transfers: list[ObservedTransfer], contract: dict[str, Any], config: AnalysisConfig
) -> AnalysisOutput:
    """Pure computation; callers must not hold a database transaction open around it."""
    payload = contract.get("_verified_context")
    context = VerifiedContext.model_validate(payload) if payload is not None else None
    return run_analysis(
        dataset_id=str(dataset_id), transfers=transfers, contract=contract, config=config, context=context
    )


def alert_fingerprint(dataset_id: uuid.UUID, formation: Formation) -> str:
    # Identity of the *pattern*, independent of snapshot: ordered route for paths/loops,
    # hub plus its counterparties on the side that defines the formation otherwise.
    if formation.kind in ("chain", "cycle"):
        members = list(formation.member_ids)
    elif formation.kind == "fan_out":
        members = [formation.subject_account_id, *sorted(formation.exit_ids)]
    else:
        members = [formation.subject_account_id, *sorted(formation.entry_ids)]
    return sha256_hex(
        canonical_json(
            {
                "dataset_id": str(dataset_id),
                "subject_kind": formation.kind,
                "currency": formation.currency,
                "members": members,
                "family_group": "STRUCTURE+TEMPORAL",
                "detector": formation.detector_id,
            }
        )
    )


def _coverage_json(a: RiskAssessment) -> dict[str, Any]:
    return {
        "limitations": list(a.coverage.limitations),
        "subject_limitations": list(a.coverage.subject_limitations),
        "boundary_accounts": list(a.coverage.boundary_accounts),
        "data_requests": [r.as_dict() for r in a.coverage.data_requests],
    }


def publish(
    session: Session,
    *,
    dataset_id: uuid.UUID,
    max_ingest_seq: int,
    out: AnalysisOutput,
    config: AnalysisConfig,
) -> uuid.UUID:
    """Write a snapshot and every linked output in the caller's transaction.

    Idempotent: identical input+config yields the same deterministic snapshot id, and a
    second publish of an existing snapshot is a no-op apart from alert ``last_seen``.
    """
    snapshot_id = uuid.UUID(out.snapshot_id)
    inserted = session.execute(
        insert(orm.GraphSnapshot)
        .values(
            id=snapshot_id,
            dataset_id=dataset_id,
            status="published",
            max_ingest_seq=max_ingest_seq,
            window_start=out.snapshot.window_start,
            window_end=out.snapshot.window_end,
            graph_version=out.graph_version,
            input_manifest_sha256=out.snapshot.input_manifest_sha256,
            config_sha256=out.config_sha256,
            policy_version=out.policy_version,
            nodes_count=out.snapshot.nodes_count,
            edges_count=out.snapshot.edges_count,
            transactions_count=out.snapshot.eligible_count,
            excluded_count=out.snapshot.excluded_count,
            formations_count=len(out.formations),
            is_partial=bool(out.partial_reasons),
            partial_reasons=out.partial_reasons,
            quarantined_results=out.quarantined,
        )
        .on_conflict_do_nothing()
        .returning(orm.GraphSnapshot.id)
    ).first()
    if inserted is None:
        existing = session.get(orm.GraphSnapshot, snapshot_id)
        if existing is None:
            # Same content identity under a different id would mean the id derivation changed.
            raise Invalid("SNAPSHOT_IDENTITY_CONFLICT", "snapshot identity exists under another id")
        _upsert_alerts(session, dataset_id, snapshot_id, out, config)
        return snapshot_id

    if out.formations:
        session.execute(
            insert(orm.Formation),
            [
                {
                    "id": uuid.UUID(f.id),
                    "snapshot_id": snapshot_id,
                    "kind": f.kind,
                    "currency": f.currency,
                    "subject_account_id": f.subject_account_id,
                    "member_ids": list(f.member_ids),
                    "entry_ids": list(f.entry_ids),
                    "exit_ids": list(f.exit_ids),
                    "features": f.features,
                    "limitations": list(f.limitations),
                    "detector_id": f.detector_id,
                    "detector_version": f.detector_version,
                    "window_start": f.window_start,
                    "window_end": f.window_end,
                }
                for f in out.formations
            ],
        )
        session.execute(
            insert(orm.Evidence),
            [
                {
                    "id": uuid.UUID(e.id),
                    "snapshot_id": snapshot_id,
                    "formation_id": uuid.UUID(e.subject_id),
                    "kind": e.kind,
                    "reason_code": e.reason_code,
                    "account_ids": list(e.account_ids),
                    "observations": e.observations,
                    "thresholds": e.thresholds,
                    "limitations": list(e.limitations),
                    "detector_version": e.detector_version,
                    "provenance_hash": e.provenance_hash,
                }
                for e in out.evidence
            ],
        )
        links = [
            {"evidence_id": uuid.UUID(e.id), "transaction_id": uuid.UUID(t)}
            for e in out.evidence
            for t in e.transaction_ids
        ]
        if links:
            session.execute(insert(orm.EvidenceTransaction), links)
        session.execute(
            insert(orm.FraudSignal),
            [
                {
                    "id": uuid.UUID(s.id),
                    "snapshot_id": snapshot_id,
                    "formation_id": uuid.UUID(s.formation_id),
                    "family": s.family,
                    "detector_id": s.detector_id,
                    "detector_version": s.detector_version,
                    "status": s.status,
                    "strength": s.strength,
                    "evidence_ids": list(s.evidence_ids),
                    "limitations": list(s.limitations),
                    "dependency_tags": list(s.dependency_tags),
                }
                for s in out.signals
            ],
        )
        session.execute(
            insert(orm.RiskAssessmentRow),
            [
                {
                    "id": uuid.UUID(a.id),
                    "snapshot_id": snapshot_id,
                    "formation_id": uuid.UUID(a.formation_id),
                    "policy_version": a.policy_version,
                    "policy_sha256": a.policy_sha256,
                    "priority": a.priority,
                    "band": a.band,
                    "signal_ids": list(a.signal_ids),
                    "supported_families": list(a.supported_families),
                    "missing_families": list(a.missing_families),
                    "coverage": _coverage_json(a),
                    "reason_codes": [r.as_dict() for r in a.reason_codes],
                }
                for a in out.assessments
            ],
        )
    _upsert_alerts(session, dataset_id, snapshot_id, out, config)
    return snapshot_id


def _upsert_alerts(
    session: Session,
    dataset_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    out: AnalysisOutput,
    config: AnalysisConfig,
) -> None:
    formations = {f.id: f for f in out.formations}
    evidence_by_formation: dict[str, list[str]] = {}
    for e in out.evidence:
        evidence_by_formation.setdefault(e.subject_id, []).append(e.provenance_hash)
    now = dt.datetime.now(dt.UTC)
    for a in out.assessments:
        if not risk_engine.opens_alert(a.band, config.risk_policy):
            continue
        f = formations[a.formation_id]
        fingerprint = alert_fingerprint(dataset_id, f)
        digest = sha256_hex(
            canonical_json({"evidence": sorted(evidence_by_formation.get(f.id, [])), "risk": a.fingerprint_payload()})
        )
        existing = session.execute(
            select(orm.Alert)
            .where(orm.Alert.dataset_id == dataset_id, orm.Alert.fingerprint == fingerprint)
            .with_for_update()
        ).scalar_one_or_none()
        if existing is None:
            session.execute(
                insert(orm.Alert)
                .values(
                    id=uuid.uuid4(),
                    dataset_id=dataset_id,
                    fingerprint=fingerprint,
                    snapshot_id=snapshot_id,
                    formation_id=uuid.UUID(f.id),
                    risk_assessment_id=uuid.UUID(a.id),
                    evidence_digest=digest,
                )
                .on_conflict_do_nothing(constraint="uq_alerts_fingerprint")
            )
            continue
        values: dict[str, Any] = {"last_seen": now}
        if existing.snapshot_id != snapshot_id:
            values.update(snapshot_id=snapshot_id, formation_id=uuid.UUID(f.id), risk_assessment_id=uuid.UUID(a.id))
        if existing.evidence_digest != digest:
            values.update(evidence_digest=digest, revision=existing.revision + 1)
        session.execute(update(orm.Alert).where(orm.Alert.id == existing.id).values(**values))
