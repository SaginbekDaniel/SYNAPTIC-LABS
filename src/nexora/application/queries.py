"""Read models for the API. Every value comes from persisted records — no demo fixtures."""

from __future__ import annotations

import datetime as dt
import uuid
from collections import deque
from typing import Any

from sqlalchemy import case as sql_case
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from nexora.application.case_service import TRANSITIONS
from nexora.application.errors import Invalid, NotFound
from nexora.persistence import orm

BAND_RANK = {"critical": 0, "high": 1, "medium": 2, "insufficient_evidence": 3, "low": 4}


def tx_dict(t: orm.Transaction) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "source_transaction_id": t.source_transaction_id,
        "sender_account_id": t.sender_account_id,
        "receiver_account_id": t.receiver_account_id,
        "amount_minor": str(int(t.amount_minor)),
        "currency": t.currency,
        "observed_date": t.observed_date,
        "occurred_at": t.occurred_at,
        "time_precision": t.time_precision,
        "status": t.status,
        "is_synthetic": t.is_synthetic,
        "ingested_at": t.ingested_at,
    }


def snapshot_dict(s: orm.GraphSnapshot) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "dataset_id": str(s.dataset_id),
        "computed_at": s.computed_at,
        "window_start": s.window_start,
        "window_end": s.window_end,
        "max_ingest_seq": s.max_ingest_seq,
        "graph_version": s.graph_version,
        "input_manifest_sha256": s.input_manifest_sha256,
        "config_sha256": s.config_sha256,
        "policy_version": s.policy_version,
        "nodes_count": s.nodes_count,
        "edges_count": s.edges_count,
        "transactions_count": s.transactions_count,
        "excluded_count": s.excluded_count,
        "formations_count": s.formations_count,
        "is_partial": s.is_partial,
        "partial_reasons": s.partial_reasons,
        "quarantined_count": len(s.quarantined_results),
    }


def job_dict(j: orm.AnalysisJob) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "dataset_id": str(j.dataset_id),
        "status": j.status,
        "attempt_count": j.attempt_count,
        "max_ingest_seq": j.max_ingest_seq,
        "snapshot_id": str(j.snapshot_id) if j.snapshot_id else None,
        "error_code": j.error_code,
        "error_summary": j.error_summary,
        "created_at": j.created_at,
        "updated_at": j.updated_at,
    }


def latest_snapshot(session: Session, dataset_id: uuid.UUID) -> orm.GraphSnapshot | None:
    return session.execute(
        select(orm.GraphSnapshot)
        .where(orm.GraphSnapshot.dataset_id == dataset_id)
        .order_by(orm.GraphSnapshot.max_ingest_seq.desc(), orm.GraphSnapshot.computed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def latest_job(session: Session, dataset_id: uuid.UUID) -> orm.AnalysisJob | None:
    return session.execute(
        select(orm.AnalysisJob)
        .where(orm.AnalysisJob.dataset_id == dataset_id)
        .order_by(orm.AnalysisJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def dataset_dict(session: Session, d: orm.Dataset) -> dict[str, Any]:
    count = session.execute(select(func.count()).where(orm.Transaction.dataset_id == d.id)).scalar_one()
    snap = latest_snapshot(session, d.id)
    job = latest_job(session, d.id)
    return {
        "id": str(d.id),
        "name": d.name,
        "source_kind": d.source_kind,
        "description": d.description,
        "time_precision": d.time_precision,
        "coverage_contract": d.coverage_contract,
        "authorized_use_note": d.authorized_use_note,
        "raw_manifest_sha256": d.raw_manifest_sha256,
        "created_at": d.created_at,
        "transactions_count": int(count),
        "latest_snapshot": snapshot_dict(snap) if snap else None,
        "latest_job": job_dict(job) if job else None,
    }


def list_datasets(session: Session, limit: int, offset: int) -> dict[str, Any]:
    total = session.execute(select(func.count()).select_from(orm.Dataset)).scalar_one()
    rows = session.execute(
        select(orm.Dataset).order_by(orm.Dataset.created_at.desc()).limit(limit).offset(offset)
    ).scalars()
    return {
        "items": [dataset_dict(session, d) for d in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def get_dataset(session: Session, dataset_id: uuid.UUID) -> orm.Dataset:
    d = session.get(orm.Dataset, dataset_id)
    if d is None:
        raise NotFound("DATASET_NOT_FOUND", "dataset does not exist")
    return d


def get_snapshot(session: Session, snapshot_id: uuid.UUID) -> orm.GraphSnapshot:
    s = session.get(orm.GraphSnapshot, snapshot_id)
    if s is None:
        raise NotFound("SNAPSHOT_NOT_FOUND", "snapshot does not exist")
    return s


def _temporal_status(f: orm.Formation) -> str | None:
    value = f.features.get("temporal_status")
    return str(value) if value is not None else None


def _alert_summary(
    session: Session, a: orm.Alert, f: orm.Formation, r: orm.RiskAssessmentRow, latest_id: uuid.UUID | None
) -> dict[str, Any]:
    c = session.execute(select(orm.Case).where(orm.Case.alert_id == a.id)).scalar_one_or_none()
    evidence_count = session.execute(select(func.count()).where(orm.Evidence.formation_id == f.id)).scalar_one()
    tx_count = session.execute(
        select(func.count(func.distinct(orm.EvidenceTransaction.transaction_id)))
        .join(orm.Evidence, orm.Evidence.id == orm.EvidenceTransaction.evidence_id)
        .where(orm.Evidence.formation_id == f.id)
    ).scalar_one()
    return {
        "id": str(a.id),
        "dataset_id": str(a.dataset_id),
        "status": a.status,
        "revision": a.revision,
        "first_seen": a.first_seen,
        "last_seen": a.last_seen,
        "snapshot_id": str(a.snapshot_id),
        "in_latest_snapshot": latest_id is not None and a.snapshot_id == latest_id,
        "formation": {
            "id": str(f.id),
            "kind": f.kind,
            "currency": f.currency,
            "subject_account_id": f.subject_account_id,
            "member_count": len(f.member_ids),
            "window_start": f.window_start,
            "window_end": f.window_end,
            "features": f.features,
        },
        "risk": {
            "priority": r.priority,
            "band": r.band,
            "policy_version": r.policy_version,
            "reason_codes": r.reason_codes,
            "supported_families": r.supported_families,
            "missing_families": r.missing_families,
        },
        "coverage_limitations": r.coverage.get("limitations", []),
        "temporal_status": _temporal_status(f),
        "evidence_count": int(evidence_count),
        "transaction_count": int(tx_count),
        "case_id": str(c.id) if c else None,
        "case_status": c.status if c else None,
    }


def list_alerts(
    session: Session,
    *,
    dataset_id: uuid.UUID | None,
    bands: list[str] | None,
    status: str | None,
    kind: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    q = (
        select(orm.Alert, orm.Formation, orm.RiskAssessmentRow)
        .join(orm.Formation, orm.Formation.id == orm.Alert.formation_id)
        .join(orm.RiskAssessmentRow, orm.RiskAssessmentRow.id == orm.Alert.risk_assessment_id)
    )
    if dataset_id is not None:
        q = q.where(orm.Alert.dataset_id == dataset_id)
    if bands:
        q = q.where(orm.RiskAssessmentRow.band.in_(bands))
    if status:
        q = q.where(orm.Alert.status == status)
    if kind:
        q = q.where(orm.Formation.kind == kind)
    total = session.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rank = sql_case(BAND_RANK, value=orm.RiskAssessmentRow.band, else_=9)
    rows = session.execute(
        q.order_by(rank, orm.RiskAssessmentRow.priority.desc().nulls_last(), orm.Alert.first_seen, orm.Alert.id)
        .limit(limit)
        .offset(offset)
    ).all()
    latest_by_ds: dict[uuid.UUID, uuid.UUID | None] = {}
    items = []
    for a, f, r in rows:
        if a.dataset_id not in latest_by_ds:
            snap = latest_snapshot(session, a.dataset_id)
            latest_by_ds[a.dataset_id] = snap.id if snap else None
        items.append(_alert_summary(session, a, f, r, latest_by_ds[a.dataset_id]))
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


def _alert_rows(session: Session, alert_id: uuid.UUID) -> tuple[orm.Alert, orm.Formation, orm.RiskAssessmentRow]:
    a = session.get(orm.Alert, alert_id)
    if a is None:
        raise NotFound("ALERT_NOT_FOUND", "alert does not exist")
    f = session.get(orm.Formation, a.formation_id)
    r = session.get(orm.RiskAssessmentRow, a.risk_assessment_id)
    assert f is not None and r is not None
    return a, f, r


def evidence_list(session: Session, formation_id: uuid.UUID) -> list[dict[str, Any]]:
    evs = (
        session.execute(
            select(orm.Evidence).where(orm.Evidence.formation_id == formation_id).order_by(orm.Evidence.kind)
        )
        .scalars()
        .all()
    )
    links = session.execute(
        select(orm.EvidenceTransaction.evidence_id, orm.EvidenceTransaction.transaction_id).where(
            orm.EvidenceTransaction.evidence_id.in_([e.id for e in evs])
        )
    ).all()
    by_ev: dict[uuid.UUID, list[str]] = {}
    for ev_id, tx_id in links:
        by_ev.setdefault(ev_id, []).append(str(tx_id))
    order = {"graph_fact": 0, "temporal_fact": 1, "counterevidence": 2, "coverage_fact": 3}
    return [
        {
            "id": str(e.id),
            "kind": e.kind,
            "reason_code": e.reason_code,
            "account_ids": e.account_ids,
            "observations": e.observations,
            "thresholds": e.thresholds,
            "limitations": e.limitations,
            "detector_version": e.detector_version,
            "provenance_hash": e.provenance_hash,
            "transaction_ids": sorted(by_ev.get(e.id, [])),
        }
        for e in sorted(evs, key=lambda e: (order.get(e.kind, 9), e.reason_code))
    ]


def alert_detail(session: Session, alert_id: uuid.UUID) -> dict[str, Any]:
    a, f, r = _alert_rows(session, alert_id)
    snap = get_snapshot(session, a.snapshot_id)
    latest = latest_snapshot(session, a.dataset_id)
    out = _alert_summary(session, a, f, r, latest.id if latest else None)
    signals = session.execute(
        select(orm.FraudSignal).where(orm.FraudSignal.formation_id == f.id).order_by(orm.FraudSignal.family)
    ).scalars()
    out["formation"].update(
        member_ids=f.member_ids,
        entry_ids=f.entry_ids,
        exit_ids=f.exit_ids,
        limitations=f.limitations,
        detector_id=f.detector_id,
        detector_version=f.detector_version,
    )
    out["coverage"] = r.coverage
    out["risk"]["policy_sha256"] = r.policy_sha256
    out["signals"] = [
        {
            "id": str(s.id),
            "family": s.family,
            "detector_id": s.detector_id,
            "detector_version": s.detector_version,
            "status": s.status,
            "strength": s.strength,
            "limitations": s.limitations,
            "dependency_tags": s.dependency_tags,
        }
        for s in signals
    ]
    out["evidence"] = evidence_list(session, f.id)
    out["snapshot"] = snapshot_dict(snap)
    return out


def alert_evidence_chain(session: Session, alert_id: uuid.UUID) -> dict[str, Any]:
    _, f, _ = _alert_rows(session, alert_id)
    evidence = evidence_list(session, f.id)
    ids = sorted({uuid.UUID(t) for e in evidence for t in e["transaction_ids"]})
    txs = session.execute(select(orm.Transaction).where(orm.Transaction.id.in_(ids))).scalars().all() if ids else []
    txs = sorted(txs, key=lambda t: (t.observed_date, t.occurred_at or t.ingested_at, t.source_transaction_id))
    return {"formation_id": str(f.id), "evidence": evidence, "transactions": [tx_dict(t) for t in txs]}


def get_transaction(session: Session, tx_id: uuid.UUID) -> dict[str, Any]:
    t = session.get(orm.Transaction, tx_id)
    if t is None:
        raise NotFound("TRANSACTION_NOT_FOUND", "transaction does not exist")
    return tx_dict(t)


def _eligible_in_snapshot(snap: orm.GraphSnapshot) -> list[Any]:
    return [
        orm.Transaction.dataset_id == snap.dataset_id,
        orm.Transaction.ingest_seq <= snap.max_ingest_seq,
        orm.Transaction.status == "posted",
        orm.Transaction.sender_account_id != orm.Transaction.receiver_account_id,
    ]


def activity(session: Session, snapshot_id: uuid.UUID) -> dict[str, Any]:
    """Daily transfer counts over the snapshot window, by source calendar date (never a clock time).

    `transactions` counts the transfers that entered the graph; `in_alerts` counts the distinct
    ones among them that are cited as evidence by a formation in this snapshot that raised an
    alert. Counts only: a per-day money sum could silently mix currencies.
    """
    snap = get_snapshot(session, snapshot_id)
    day = orm.Transaction.observed_date
    totals = dict(
        session.execute(select(day, func.count()).where(*_eligible_in_snapshot(snap)).group_by(day)).all()
    )
    alerted = (
        select(orm.EvidenceTransaction.transaction_id)
        .join(orm.Evidence, orm.Evidence.id == orm.EvidenceTransaction.evidence_id)
        .join(orm.Alert, orm.Alert.formation_id == orm.Evidence.formation_id)
        .where(orm.Evidence.snapshot_id == snap.id)
    )
    flagged = dict(
        session.execute(
            select(day, func.count(func.distinct(orm.Transaction.id)))
            .where(*_eligible_in_snapshot(snap), orm.Transaction.id.in_(alerted))
            .group_by(day)
        ).all()
    )
    start = snap.window_start or (min(totals) if totals else None)
    end = snap.window_end or (max(totals) if totals else None)
    days: list[dict[str, Any]] = []
    if start is not None and end is not None:
        d = start
        while d <= end:
            days.append({"date": d, "transactions": int(totals.get(d, 0)), "in_alerts": int(flagged.get(d, 0))})
            d += dt.timedelta(days=1)
    return {"snapshot_id": str(snap.id), "days": days}


def account_summary(session: Session, snapshot_id: uuid.UUID, account_id: str) -> dict[str, Any]:
    snap = get_snapshot(session, snapshot_id)
    base = _eligible_in_snapshot(snap)
    out_row = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(orm.Transaction.amount_minor), 0),
            func.count(func.distinct(orm.Transaction.receiver_account_id)),
        ).where(*base, orm.Transaction.sender_account_id == account_id)
    ).one()
    in_row = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(orm.Transaction.amount_minor), 0),
            func.count(func.distinct(orm.Transaction.sender_account_id)),
        ).where(*base, orm.Transaction.receiver_account_id == account_id)
    ).one()
    found = (out_row[0] + in_row[0]) > 0
    dataset = session.get(orm.Dataset, snap.dataset_id)
    boundary = set((dataset.coverage_contract if dataset else {}).get("boundary_account_ids") or [])
    formations = []
    if found:
        rows = session.execute(
            select(orm.Formation, orm.RiskAssessmentRow, orm.Alert.id)
            .join(orm.RiskAssessmentRow, orm.RiskAssessmentRow.formation_id == orm.Formation.id)
            .outerjoin(orm.Alert, orm.Alert.risk_assessment_id == orm.RiskAssessmentRow.id)
            .where(
                orm.Formation.snapshot_id == snapshot_id,
                or_(
                    orm.Formation.member_ids.contains([account_id]),
                    orm.Formation.exit_ids.contains([account_id]),
                ),
            )
        ).all()
        rank = BAND_RANK
        for f, r, alert_id in sorted(rows, key=lambda x: (rank.get(x[1].band, 9), -(x[1].priority or 0))):
            formations.append(
                {
                    "formation_id": str(f.id),
                    "kind": f.kind,
                    "role": "subject"
                    if f.subject_account_id == account_id
                    else ("exit" if account_id in f.exit_ids else "member"),
                    "band": r.band,
                    "priority": r.priority,
                    "temporal_status": _temporal_status(f),
                    "alert_id": str(alert_id) if alert_id else None,
                }
            )
    return {
        "snapshot_id": str(snapshot_id),
        "account_id": account_id,
        "found": found,
        "is_boundary": account_id in boundary,
        "outgoing_count": int(out_row[0]),
        "outgoing_minor": str(int(out_row[1])),
        "distinct_receivers": int(out_row[2]),
        "incoming_count": int(in_row[0]),
        "incoming_minor": str(int(in_row[1])),
        "distinct_senders": int(in_row[2]),
        "formations": formations,
    }


def neighborhood(
    session: Session, snapshot_id: uuid.UUID, account_id: str, depth: int, max_nodes: int, max_edges: int
) -> dict[str, Any]:
    snap = get_snapshot(session, snapshot_id)
    base = _eligible_in_snapshot(snap)
    dataset = session.get(orm.Dataset, snap.dataset_id)
    boundary = set((dataset.coverage_contract if dataset else {}).get("boundary_account_ids") or [])
    agg = (
        select(
            orm.Transaction.sender_account_id,
            orm.Transaction.receiver_account_id,
            orm.Transaction.currency,
            func.sum(orm.Transaction.amount_minor),
            func.count(),
            func.min(orm.Transaction.observed_date),
            func.max(orm.Transaction.observed_date),
        )
        .where(*base)
        .group_by(orm.Transaction.sender_account_id, orm.Transaction.receiver_account_id, orm.Transaction.currency)
    )
    seen = {account_id: 0}
    queue: deque[str] = deque([account_id])
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    truncated = False
    while queue:
        node = queue.popleft()
        d = seen[node]
        if d >= depth:
            continue
        rows = session.execute(
            agg.where(or_(orm.Transaction.sender_account_id == node, orm.Transaction.receiver_account_id == node))
        ).all()
        for snd, rcv, cur, total, n, first, last in sorted(rows, key=lambda r: (-int(r[3]), r[0], r[1])):
            other = rcv if snd == node else snd
            if other not in seen:
                if len(seen) >= max_nodes:
                    truncated = True
                    continue
                seen[other] = d + 1
                queue.append(other)
            key = (snd, rcv, cur)
            if key not in edges:
                if len(edges) >= max_edges:
                    truncated = True
                    continue
                edges[key] = {
                    "sender": snd,
                    "receiver": rcv,
                    "currency": cur,
                    "amount_minor": str(int(total)),
                    "n_transactions": int(n),
                    "first_date": first,
                    "last_date": last,
                }
    found = len(seen) > 1 or bool(edges)
    return {
        "snapshot_id": str(snapshot_id),
        "center": account_id,
        "found": found,
        "depth": depth,
        "truncated": truncated,
        "limits": {"max_nodes": max_nodes, "max_edges": max_edges},
        "nodes": [
            {"account_id": a, "hop": h, "is_boundary": a in boundary}
            for a, h in sorted(seen.items(), key=lambda x: (x[1], x[0]))
        ],
        "edges": [edges[k] for k in sorted(edges)],
    }


def snapshot_transactions(
    session: Session,
    snapshot_id: uuid.UUID,
    account_id: str | None,
    counterparty_id: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    snap = get_snapshot(session, snapshot_id)
    q = select(orm.Transaction).where(
        orm.Transaction.dataset_id == snap.dataset_id, orm.Transaction.ingest_seq <= snap.max_ingest_seq
    )
    if counterparty_id and not account_id:
        raise Invalid("COUNTERPARTY_REQUIRES_ACCOUNT", "counterparty_id requires account_id")
    if account_id and counterparty_id:
        q = q.where(
            or_(
                (orm.Transaction.sender_account_id == account_id)
                & (orm.Transaction.receiver_account_id == counterparty_id),
                (orm.Transaction.sender_account_id == counterparty_id)
                & (orm.Transaction.receiver_account_id == account_id),
            )
        )
    elif account_id:
        q = q.where(
            or_(
                orm.Transaction.sender_account_id == account_id,
                orm.Transaction.receiver_account_id == account_id,
            )
        )
    total = session.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = session.execute(
        q.order_by(orm.Transaction.observed_date, orm.Transaction.occurred_at, orm.Transaction.source_transaction_id)
        .limit(limit)
        .offset(offset)
    ).scalars()
    return {"items": [tx_dict(t) for t in rows], "total": int(total), "limit": limit, "offset": offset}


def case_dict(session: Session, c: orm.Case) -> dict[str, Any]:
    notes = session.execute(
        select(orm.CaseNote).where(orm.CaseNote.case_id == c.id).order_by(orm.CaseNote.created_at)
    ).scalars()
    return {
        "id": str(c.id),
        "alert_id": str(c.alert_id),
        "title": c.title,
        "status": c.status,
        "assigned_to": c.assigned_to,
        "opened_at": c.opened_at,
        "closed_at": c.closed_at,
        "decision": c.decision,
        "decision_reason": c.decision_reason,
        "version": c.version,
        "allowed_transitions": sorted(TRANSITIONS.get(c.status, frozenset())),
        "notes": [{"id": str(n.id), "author": n.author, "body": n.body, "created_at": n.created_at} for n in notes],
    }


def get_case(session: Session, case_id: uuid.UUID) -> dict[str, Any]:
    c = session.get(orm.Case, case_id)
    if c is None:
        raise NotFound("CASE_NOT_FOUND", "case does not exist")
    return case_dict(session, c)


def list_cases(
    session: Session, *, dataset_id: uuid.UUID | None, status: str | None, limit: int, offset: int
) -> dict[str, Any]:
    q = (
        select(orm.Case, orm.Alert, orm.RiskAssessmentRow)
        .join(orm.Alert, orm.Alert.id == orm.Case.alert_id)
        .join(orm.RiskAssessmentRow, orm.RiskAssessmentRow.id == orm.Alert.risk_assessment_id)
    )
    if dataset_id:
        q = q.where(orm.Alert.dataset_id == dataset_id)
    if status:
        q = q.where(orm.Case.status == status)
    total = session.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = session.execute(q.order_by(orm.Case.opened_at.desc()).limit(limit).offset(offset)).all()
    items = []
    for c, a, r in rows:
        d = case_dict(session, c)
        d.pop("notes")
        d.update(dataset_id=str(a.dataset_id), band=r.band, priority=r.priority)
        items.append(d)
    return {"items": items, "total": int(total), "limit": limit, "offset": offset}


def case_audit(session: Session, case_id: uuid.UUID) -> list[dict[str, Any]]:
    if session.get(orm.Case, case_id) is None:
        raise NotFound("CASE_NOT_FOUND", "case does not exist")
    rows = session.execute(
        select(orm.AuditEvent)
        .where(orm.AuditEvent.entity_type == "case", orm.AuditEvent.entity_id == str(case_id))
        .order_by(orm.AuditEvent.id)
    ).scalars()
    return [
        {
            "id": e.id,
            "actor": e.actor,
            "action": e.action,
            "before": e.before_json,
            "after": e.after_json,
            "reason": e.reason,
            "request_id": e.request_id,
            "created_at": e.created_at,
        }
        for e in rows
    ]


def overview(session: Session, dataset_id: uuid.UUID) -> dict[str, Any]:
    d = get_dataset(session, dataset_id)
    bands = dict(
        session.execute(
            select(orm.RiskAssessmentRow.band, func.count())
            .join(orm.Alert, orm.Alert.risk_assessment_id == orm.RiskAssessmentRow.id)
            .where(orm.Alert.dataset_id == dataset_id, orm.Alert.status != "closed")
            .group_by(orm.RiskAssessmentRow.band)
        ).all()
    )
    case_status = dict(
        session.execute(
            select(orm.Case.status, func.count())
            .join(orm.Alert, orm.Alert.id == orm.Case.alert_id)
            .where(orm.Alert.dataset_id == dataset_id)
            .group_by(orm.Case.status)
        ).all()
    )
    snap = latest_snapshot(session, dataset_id)
    by_kind: dict[str, int] = {}
    temporal: dict[str, int] = {}
    if snap:
        for kind, n in session.execute(
            select(orm.Formation.kind, func.count())
            .where(orm.Formation.snapshot_id == snap.id)
            .group_by(orm.Formation.kind)
        ).all():
            by_kind[kind] = int(n)
        for status, n in session.execute(
            select(orm.FraudSignal.status, func.count())
            .where(orm.FraudSignal.snapshot_id == snap.id, orm.FraudSignal.family == "TEMPORAL")
            .group_by(orm.FraudSignal.status)
        ).all():
            temporal[status] = int(n)
    return {
        "dataset": dataset_dict(session, d),
        "open_alerts_by_band": {k: int(v) for k, v in bands.items()},
        "cases_by_status": {k: int(v) for k, v in case_status.items()},
        "formations_by_kind": by_kind,
        "temporal_status_counts": temporal,
    }
