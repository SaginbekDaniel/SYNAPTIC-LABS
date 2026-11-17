import datetime as dt
import uuid

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from nexora.analytics.config import default_config
from nexora.application import analysis_service, case_service, ingest_service
from nexora.application.errors import Conflict, Invalid
from nexora.evaluation.generator import generate
from nexora.persistence import orm
from nexora.persistence.db import session_scope
from nexora.worker.runner import run_once

pytestmark = pytest.mark.integration
CFG = default_config()


def _synthetic(factory, suite="demo-v1", seed=2026):
    with session_scope(factory) as s:
        ds, _, report = ingest_service.create_synthetic_dataset(s, suite=suite, seed=seed)
        return ds.id, report


def _analyse(factory, dataset_id):
    with session_scope(factory) as s:
        job = analysis_service.request_analysis(s, dataset_id=dataset_id, requested_by="t", config=CFG)
        job_id = job.id
    assert run_once(factory, config=CFG) == job_id
    with session_scope(factory) as s:
        return s.get(orm.AnalysisJob, job_id)


def test_reimport_is_idempotent_and_conflicts_quarantined(factory):  # DATA-004, DATA-005, reliability #5
    ds_id, report = _synthetic(factory)
    assert report.accepted == report.processed > 0
    rows = list(enumerate(generate("demo-v1", 2026).rows, 1))
    with session_scope(factory) as s:
        ds = s.get(orm.Dataset, ds_id)
        _, again = ingest_service.ingest_rows(
            s,
            dataset=ds,
            rows=rows,
            source_id="synthetic:demo-v1:2026",
            content_sha256="x",
            file_name=None,
            is_synthetic=True,
        )
    assert again.accepted == 0 and again.duplicated_identical == len(rows)
    tampered = [(1, {**rows[0][1], "amount_minor": "1"})]
    with session_scope(factory) as s:
        ds = s.get(orm.Dataset, ds_id)
        _, conflict = ingest_service.ingest_rows(
            s,
            dataset=ds,
            rows=tampered,
            source_id="synthetic:demo-v1:2026",
            content_sha256="y",
            file_name=None,
            is_synthetic=True,
        )
    assert conflict.error_codes == {"CONFLICTING_TRANSACTION_DUPLICATE": 1}
    with session_scope(factory) as s:
        n = s.execute(select(func.count()).where(orm.Transaction.dataset_id == ds_id)).scalar_one()
        total = s.execute(
            select(func.sum(orm.Transaction.amount_minor)).where(orm.Transaction.dataset_id == ds_id)
        ).scalar_one()
    assert n == report.accepted
    assert int(total) == sum(int(r["amount_minor"]) for _, r in rows)  # exact NUMERIC money, no float drift


def test_analysis_publishes_once_and_evidence_resolves(factory):  # JOB-002, EVID-001
    ds_id, _ = _synthetic(factory, seed=31)
    job = _analyse(factory, ds_id)
    assert job.status == "succeeded" and job.snapshot_id is not None
    with session_scope(factory) as s:
        again = analysis_service.request_analysis(s, dataset_id=ds_id, requested_by="t", config=CFG)
        assert again.id == job.id  # identical watermark+config -> same job (idempotency key)
        transfers, contract = analysis_service.load_inputs(s, ds_id, job.max_ingest_seq)
    out = analysis_service.compute(ds_id, transfers, contract, CFG)
    with session_scope(factory) as s:
        before = s.execute(select(func.count()).where(orm.Alert.dataset_id == ds_id)).scalar_one()
        sid = analysis_service.publish(s, dataset_id=ds_id, max_ingest_seq=job.max_ingest_seq, out=out, config=CFG)
    with session_scope(factory) as s:
        assert sid == job.snapshot_id
        assert s.execute(select(func.count()).where(orm.GraphSnapshot.dataset_id == ds_id)).scalar_one() == 1
        assert s.execute(select(func.count()).where(orm.Alert.dataset_id == ds_id)).scalar_one() == before > 0
        dangling = s.execute(
            text(
                "SELECT count(*) FROM evidence_transactions et JOIN transactions t ON t.id = et.transaction_id "
                "JOIN evidence e ON e.id = et.evidence_id JOIN graph_snapshots g ON g.id = e.snapshot_id "
                "WHERE t.dataset_id <> g.dataset_id OR t.ingest_seq > g.max_ingest_seq"
            )
        ).scalar_one()
        assert dangling == 0


def test_expired_lease_is_reclaimed(factory):  # JOB-001
    ds_id, _ = _synthetic(factory, seed=32)
    with session_scope(factory) as s:
        job = analysis_service.request_analysis(s, dataset_id=ds_id, requested_by="t", config=CFG)
        job_id = job.id
        # Simulate a worker that claimed the job and crashed: lease already expired.
        s.execute(
            update(orm.AnalysisJob)
            .where(orm.AnalysisJob.id == job_id)
            .values(
                status="running",
                lease_owner="dead-worker",
                lease_until=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=5),
                attempt_count=1,
            )
        )
    assert run_once(factory, owner="live-worker", config=CFG) == job_id
    with session_scope(factory) as s:
        job = s.get(orm.AnalysisJob, job_id)
        assert job.status == "succeeded" and job.attempt_count == 2 and job.lease_owner is None
        assert s.execute(select(func.count()).where(orm.GraphSnapshot.dataset_id == ds_id)).scalar_one() == 1


def test_failed_job_retries_then_fails_visibly(factory, monkeypatch):
    ds_id, _ = _synthetic(factory, seed=33)
    with session_scope(factory) as s:
        job_id = analysis_service.request_analysis(s, dataset_id=ds_id, requested_by="t", config=CFG).id

    def boom(*a, **k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(analysis_service, "compute", boom)
    for _ in range(3):
        assert run_once(factory, config=CFG) == job_id
    with session_scope(factory) as s:
        job = s.get(orm.AnalysisJob, job_id)
        assert job.status == "failed" and job.error_code == "ANALYSIS_FAILED" and job.attempt_count == 3
    assert run_once(factory, config=CFG) is None


def _first_alert(factory, ds_id):
    with session_scope(factory) as s:
        return s.execute(select(orm.Alert.id).where(orm.Alert.dataset_id == ds_id).limit(1)).scalar_one()


def test_case_lifecycle_conflict_and_audit(factory):  # CASE-001..003
    ds_id, _ = _synthetic(factory, seed=34)
    _analyse(factory, ds_id)
    alert_id = _first_alert(factory, ds_id)
    with session_scope(factory) as s:
        case, created = case_service.open_case(s, alert_id=alert_id, actor="ana", request_id="r1")
        case_id = case.id
    assert created
    with session_scope(factory) as s:
        same, created2 = case_service.open_case(s, alert_id=alert_id, actor="ana", request_id="r2")
    assert same.id == case_id and not created2
    with session_scope(factory) as s:
        case_service.transition(
            s,
            case_id=case_id,
            to_status="investigating",
            expected_version=1,
            reason=None,
            actor="ana",
            request_id="r3",
        )
    with pytest.raises(Invalid) as reason_missing, session_scope(factory) as s:
        case_service.transition(
            s,
            case_id=case_id,
            to_status="escalated",
            expected_version=2,
            reason="  ",
            actor="ana",
            request_id="r4",
        )
    assert reason_missing.value.code == "CASE_REASON_REQUIRED"
    with session_scope(factory) as s:
        case_service.transition(
            s,
            case_id=case_id,
            to_status="escalated",
            expected_version=2,
            reason="chain confirmed",
            actor="ana",
            request_id="r5",
        )
    # A second analyst acting on the stale version loses; nothing is overwritten.
    with pytest.raises(Conflict), session_scope(factory) as s:
        case_service.transition(
            s,
            case_id=case_id,
            to_status="dismissed",
            expected_version=2,
            reason="stale",
            actor="bob",
            request_id="r6",
        )
    with pytest.raises(Invalid), session_scope(factory) as s:
        case_service.transition(
            s,
            case_id=case_id,
            to_status="new",
            expected_version=3,
            reason="x",
            actor="ana",
            request_id="r7",
        )
    with session_scope(factory) as s:
        case_service.transition(
            s,
            case_id=case_id,
            to_status="closed",
            expected_version=3,
            reason="filed",
            actor="ana",
            request_id="r8",
        )
        case_service.transition(
            s,
            case_id=case_id,
            to_status="reopened",
            expected_version=4,
            reason="new info",
            actor="ana",
            request_id="r9",
        )
    with session_scope(factory) as s:
        c = s.get(orm.Case, case_id)
        assert c.status == "reopened" and c.version == 5 and c.decision == "escalated" and c.closed_at is None
        actions = (
            s.execute(
                select(orm.AuditEvent.action)
                .where(orm.AuditEvent.entity_id == str(case_id))
                .order_by(orm.AuditEvent.id)
            )
            .scalars()
            .all()
        )
    assert actions == ["case.opened", "case.investigating", "case.escalated", "case.closed", "case.reopened"]


def test_audit_log_is_append_only(factory):
    with session_scope(factory) as s:
        s.add(orm.AuditEvent(actor="t", action="probe", entity_type="test", entity_id=str(uuid.uuid4())))
    for stmt in ("UPDATE audit_events SET actor = 'x'", "DELETE FROM audit_events", "TRUNCATE audit_events"):
        with pytest.raises(DBAPIError), session_scope(factory) as s:
            s.execute(text(stmt))
