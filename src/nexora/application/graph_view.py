"""Investigation-graph read model (graph-view-v1).

Everything here is read from a published snapshot: transfers that entered the snapshot's
aggregates, formations, their stored risk assessments and the transactions their evidence cites.
Nothing is scored, inferred or recomputed for display. Two bounded views:

* ``overview`` — the top formations of a snapshot (server ranking: band, then priority) as clusters
  of their member accounts, plus the observed transfers among those accounts.
* ``local`` — the 1–2 hop transfer neighbourhood of one account, annotated with the formations each
  account belongs to.

Edges are always *observed transfers* aggregated per (sender, receiver, currency). An edge is
marked as formation evidence only when a transaction cited by that formation's evidence lies on it;
the edge then carries the temporal status of those formations — never a status of its own.
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from nexora.application.errors import Invalid, NotFound
from nexora.persistence import orm

GRAPH_VIEW_VERSION = "graph-view-v1"
BAND_RANK = {"critical": 0, "high": 1, "medium": 2, "insufficient_evidence": 3, "low": 4}


@dataclass(frozen=True)
class GraphBudget:
    max_nodes: int
    max_edges: int
    max_formations: int


def _snapshot(session: Session, snapshot_id: uuid.UUID) -> orm.GraphSnapshot:
    snap = session.get(orm.GraphSnapshot, snapshot_id)
    if snap is None:
        raise NotFound("SNAPSHOT_NOT_FOUND", "snapshot does not exist")
    return snap


def eligible(snap: orm.GraphSnapshot) -> list[Any]:
    """Exactly the transfers the snapshot's graph aggregates (see analytics.graph_builder)."""
    return [
        orm.Transaction.dataset_id == snap.dataset_id,
        orm.Transaction.ingest_seq <= snap.max_ingest_seq,
        orm.Transaction.status == "posted",
        orm.Transaction.sender_account_id != orm.Transaction.receiver_account_id,
    ]


def _aggregate() -> Any:
    t = orm.Transaction
    return select(
        t.sender_account_id,
        t.receiver_account_id,
        t.currency,
        func.sum(t.amount_minor),
        func.count(),
        func.min(t.observed_date),
        func.max(t.observed_date),
    ).group_by(t.sender_account_id, t.receiver_account_id, t.currency)


def _edge_row(snd: str, rcv: str, cur: str, total: Any, n: Any, first: Any, last: Any) -> dict[str, Any]:
    return {
        "sender": snd,
        "receiver": rcv,
        "currency": cur,
        "amount_minor": str(int(total)),
        "n_transactions": int(n),
        "first_date": first,
        "last_date": last,
    }


def bfs_neighborhood(
    session: Session, snap: orm.GraphSnapshot, account_id: str, depth: int, max_nodes: int, max_edges: int
) -> tuple[dict[str, int], dict[tuple[str, str, str], dict[str, Any]], bool]:
    """Breadth-first transfer neighbourhood. Heaviest edges are kept first when a budget is hit."""
    agg = _aggregate().where(*eligible(snap))
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
        for snd, rcv, cur, total, n, first, last in sorted(rows, key=lambda r: (-int(r[3]), r[0], r[1], r[2])):
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
                edges[key] = _edge_row(snd, rcv, cur, total, n, first, last)
    return seen, edges, truncated


def _boundary(session: Session, snap: orm.GraphSnapshot) -> set[str]:
    dataset = session.get(orm.Dataset, snap.dataset_id)
    return set((dataset.coverage_contract if dataset else {}).get("boundary_account_ids") or [])


def _formations(
    session: Session, snapshot_id: uuid.UUID, bands: Sequence[str] | None, kinds: Sequence[str] | None
) -> list[dict[str, Any]]:
    q = (
        select(orm.Formation, orm.RiskAssessmentRow, orm.Alert.id)
        .join(orm.RiskAssessmentRow, orm.RiskAssessmentRow.formation_id == orm.Formation.id)
        .outerjoin(orm.Alert, orm.Alert.risk_assessment_id == orm.RiskAssessmentRow.id)
        .where(orm.Formation.snapshot_id == snapshot_id)
    )
    if bands:
        q = q.where(orm.RiskAssessmentRow.band.in_(bands))
    if kinds:
        q = q.where(orm.Formation.kind.in_(kinds))
    out: list[dict[str, Any]] = []
    for f, r, alert_id in session.execute(q).all():
        temporal = f.features.get("temporal_status")
        out.append(
            {
                "id": str(f.id),
                "kind": f.kind,
                "currency": f.currency,
                "subject_account_id": f.subject_account_id,
                "member_ids": list(f.member_ids),
                "entry_ids": list(f.entry_ids),
                "exit_ids": list(f.exit_ids),
                "band": r.band,
                "priority": r.priority,
                "temporal_status": str(temporal) if temporal is not None else None,
                "alert_id": str(alert_id) if alert_id else None,
            }
        )
    # Server ranking, identical to the Review Queue: band first, then priority, then a stable tiebreak.
    out.sort(key=lambda f: (BAND_RANK.get(f["band"], 9), -(f["priority"] or 0), f["id"]))
    return out


def _accounts_of(f: dict[str, Any]) -> list[str]:
    ordered = [f["subject_account_id"], *f["member_ids"], *f["exit_ids"]]
    return list(dict.fromkeys(ordered))


def _role(f: dict[str, Any], account: str) -> str:
    if account == f["subject_account_id"]:
        return "subject"
    if account in f["entry_ids"]:
        return "entry"
    if account in f["exit_ids"]:
        return "exit"
    return "member"


def _evidence_pairs(session: Session, formation_ids: list[str]) -> dict[tuple[str, str, str], set[str]]:
    """(sender, receiver, currency) → formations whose evidence cites a transaction on that pair."""
    if not formation_ids:
        return {}
    t = orm.Transaction
    rows = session.execute(
        select(t.sender_account_id, t.receiver_account_id, t.currency, orm.Evidence.formation_id)
        .join(orm.EvidenceTransaction, orm.EvidenceTransaction.transaction_id == t.id)
        .join(orm.Evidence, orm.Evidence.id == orm.EvidenceTransaction.evidence_id)
        .where(orm.Evidence.formation_id.in_([uuid.UUID(i) for i in formation_ids]))
        .distinct()
    ).all()
    pairs: dict[tuple[str, str, str], set[str]] = {}
    for snd, rcv, cur, fid in rows:
        pairs.setdefault((snd, rcv, cur), set()).add(str(fid))
    return pairs


def _snapshot_meta(snap: orm.GraphSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": str(snap.id),
        "dataset_id": str(snap.dataset_id),
        "graph_version": snap.graph_version,
        "policy_version": snap.policy_version,
        "config_sha256": snap.config_sha256,
        "input_manifest_sha256": snap.input_manifest_sha256,
        "computed_at": snap.computed_at,
        "view_version": GRAPH_VIEW_VERSION,
    }


def _assemble(
    snap: orm.GraphSnapshot,
    mode: str,
    center: str | None,
    hops: dict[str, int | None],
    edges: dict[tuple[str, str, str], dict[str, Any]],
    formations: list[dict[str, Any]],
    evidence: dict[tuple[str, str, str], set[str]],
    boundary: set[str],
    budget: GraphBudget,
    truncation: list[str],
) -> dict[str, Any]:
    by_id = {f["id"]: f for f in formations}
    membership: dict[str, list[dict[str, str]]] = {}
    for f in formations:
        for a in _accounts_of(f):
            if a in hops:
                membership.setdefault(a, []).append({"formation_id": f["id"], "role": _role(f, a)})

    nodes = []
    for account, hop in sorted(hops.items(), key=lambda x: (x[1] if x[1] is not None else 0, x[0])):
        refs = membership.get(account, [])
        # Strongest *stored* assessment among the formations the account belongs to. Never derived
        # from position, degree or amount.
        best = min(
            (by_id[r["formation_id"]] for r in refs),
            key=lambda f: (BAND_RANK.get(f["band"], 9), -(f["priority"] or 0)),
            default=None,
        )
        nodes.append(
            {
                "account_id": account,
                "hop": hop,
                "is_boundary": account in boundary,
                "formations": refs,
                "band": best["band"] if best else None,
                "priority": best["priority"] if best else None,
            }
        )

    out_edges = []
    for key in sorted(edges):
        e = dict(edges[key])
        fids = sorted(fid for fid in evidence.get(key, set()) if fid in by_id)
        statuses = sorted({by_id[fid]["temporal_status"] or "unavailable" for fid in fids})
        e["kind"] = "observed_transfer"
        e["evidence_formation_ids"] = fids
        e["temporal_statuses"] = statuses
        out_edges.append(e)

    used = {r["formation_id"] for refs in membership.values() for r in refs}
    return {
        **_snapshot_meta(snap),
        "mode": mode,
        "center": center,
        "found": bool(nodes) and (mode == "overview" or len(nodes) > 1 or bool(out_edges)),
        "formations": [
            {k: v for k, v in f.items() if k not in ("member_ids", "entry_ids", "exit_ids")}
            | {"account_count": len(_accounts_of(f))}
            for f in formations
            if f["id"] in used
        ],
        "nodes": nodes,
        "edges": out_edges,
        "limits": {
            "max_nodes": budget.max_nodes,
            "max_edges": budget.max_edges,
            "max_formations": budget.max_formations,
            "truncated": bool(truncation),
            "reasons": truncation,
        },
    }


def overview(
    session: Session,
    snapshot_id: uuid.UUID,
    budget: GraphBudget,
    bands: Sequence[str] | None = None,
    kinds: Sequence[str] | None = None,
) -> dict[str, Any]:
    snap = _snapshot(session, snapshot_id)
    ranked = _formations(session, snapshot_id, bands, kinds)
    truncation: list[str] = []
    chosen: list[dict[str, Any]] = []
    accounts: dict[str, int | None] = {}
    for f in ranked:
        if len(chosen) >= budget.max_formations:
            truncation.append("max_formations")
            break
        members = _accounts_of(f)
        new = [a for a in members if a not in accounts]
        if len(accounts) + len(new) > budget.max_nodes:
            # Whole formations or nothing: a half-drawn formation would misstate its shape.
            truncation.append("max_nodes")
            break
        chosen.append(f)
        for a in new:
            accounts[a] = None

    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    if accounts:
        ids = list(accounts)
        rows = session.execute(
            _aggregate().where(
                *eligible(snap),
                orm.Transaction.sender_account_id.in_(ids),
                orm.Transaction.receiver_account_id.in_(ids),
            )
        ).all()
        evidence = _evidence_pairs(session, [f["id"] for f in chosen])
        # Evidence edges first, then the heaviest; a stable tiebreak keeps the view reproducible.
        rows = sorted(rows, key=lambda r: (0 if (r[0], r[1], r[2]) in evidence else 1, -int(r[3]), r[0], r[1], r[2]))
        for snd, rcv, cur, total, n, first, last in rows:
            if len(edges) >= budget.max_edges:
                truncation.append("max_edges")
                break
            edges[(snd, rcv, cur)] = _edge_row(snd, rcv, cur, total, n, first, last)
    else:
        evidence = {}
    return _assemble(
        snap, "overview", None, accounts, edges, chosen, evidence, _boundary(session, snap), budget, truncation
    )


def local(
    session: Session,
    snapshot_id: uuid.UUID,
    account_id: str,
    depth: int,
    budget: GraphBudget,
    bands: Sequence[str] | None = None,
    kinds: Sequence[str] | None = None,
) -> dict[str, Any]:
    snap = _snapshot(session, snapshot_id)
    seen, edges, truncated = bfs_neighborhood(session, snap, account_id, depth, budget.max_nodes, budget.max_edges)
    touching = [f for f in _formations(session, snapshot_id, bands, kinds) if any(a in seen for a in _accounts_of(f))]
    formations = touching[: budget.max_formations]
    evidence = _evidence_pairs(session, [f["id"] for f in formations])
    hops: dict[str, int | None] = dict(seen)
    truncation = (["max_nodes_or_edges"] if truncated else []) + (
        ["max_formations"] if len(touching) > len(formations) else []
    )
    return _assemble(
        snap,
        "local",
        account_id,
        hops,
        edges,
        formations,
        evidence,
        _boundary(session, snap),
        budget,
        truncation,
    )


def edge_transactions(
    session: Session,
    snapshot_id: uuid.UUID,
    sender: str,
    receiver: str,
    currency: str,
    limit: int,
    offset: int,
) -> tuple[list[orm.Transaction], int]:
    """Exactly the source transfers aggregated into one directed edge of the graph."""
    snap = _snapshot(session, snapshot_id)
    if sender == receiver:
        raise Invalid("SELF_EDGE", "self-transfers are never graph edges")
    t = orm.Transaction
    where = [
        *eligible(snap),
        tuple_(t.sender_account_id, t.receiver_account_id) == tuple_(sender, receiver),
        t.currency == currency,
    ]
    total = session.execute(select(func.count()).where(*where)).scalar_one()
    rows = session.execute(
        select(t)
        .where(*where)
        .order_by(t.observed_date, t.occurred_at, t.source_transaction_id)
        .limit(limit)
        .offset(offset)
    ).scalars()
    return list(rows), int(total)
