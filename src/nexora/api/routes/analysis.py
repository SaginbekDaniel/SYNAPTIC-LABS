from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from nexora.api import schemas
from nexora.api.deps import SessionDep, actor, parse_uuid, requires
from nexora.application import analysis_service, graph_view, queries
from nexora.application.errors import Invalid, NotFound
from nexora.persistence import orm

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analysis/jobs", response_model=schemas.Job, status_code=202, dependencies=[requires("analyst")])
def create_job(
    body: schemas.AnalysisJobRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    who: Annotated[str, Depends(actor)],
) -> Any:
    job = analysis_service.request_analysis(
        session,
        dataset_id=parse_uuid(body.dataset_id, "dataset_id"),
        requested_by=who,
        config=request.app.state.analysis_config,
        idempotency_key=body.idempotency_key,
    )
    session.flush()
    response.headers["Location"] = f"/api/v1/analysis/jobs/{job.id}"
    return queries.job_dict(job)


@router.get("/analysis/jobs/{job_id}", response_model=schemas.Job)
def get_job(job_id: str, session: SessionDep) -> Any:
    job = session.get(orm.AnalysisJob, parse_uuid(job_id, "job_id"))
    if job is None:
        raise NotFound("JOB_NOT_FOUND", "analysis job does not exist")
    return queries.job_dict(job)


@router.get("/analysis/snapshots/{snapshot_id}", response_model=schemas.Snapshot)
def get_snapshot(snapshot_id: str, session: SessionDep) -> Any:
    return queries.snapshot_dict(queries.get_snapshot(session, parse_uuid(snapshot_id, "snapshot_id")))


@router.get("/snapshots/{snapshot_id}/neighborhood", response_model=schemas.Neighborhood, tags=["graph"])
def neighborhood(
    snapshot_id: str,
    request: Request,
    session: SessionDep,
    account_id: str = Query(min_length=1, max_length=128),
    depth: int = Query(1, ge=1),
    max_nodes: int = Query(150, ge=1),
) -> Any:
    s = request.app.state.settings
    # Clamp to server-side caps and report the effective limits (SEC-002).
    return queries.neighborhood(
        session,
        parse_uuid(snapshot_id, "snapshot_id"),
        account_id,
        depth=min(depth, s.graph_max_depth),
        max_nodes=min(max_nodes, s.graph_max_nodes),
        max_edges=s.graph_max_edges,
    )


@router.get("/snapshots/{snapshot_id}/graph", response_model=schemas.InvestigationGraph, tags=["graph"])
def investigation_graph(
    snapshot_id: str,
    request: Request,
    session: SessionDep,
    mode: schemas.GraphMode = "overview",
    account_id: str | None = Query(None, min_length=1, max_length=128),
    depth: int = Query(1, ge=1, le=2),
    max_nodes: int = Query(200, ge=1),
    max_formations: int = Query(25, ge=1),
    band: Annotated[list[schemas.Band] | None, Query(max_length=5)] = None,
    kind: Annotated[list[schemas.FormationKind] | None, Query(max_length=4)] = None,
) -> Any:
    """Bounded investigation graph from a published snapshot (graph-view-v1).

    ``overview``: top formations by stored band/priority, whole formations only, with the observed
    transfers among their accounts. ``local``: the 1–2 hop transfer neighbourhood of ``account_id``.
    Requested budgets are clamped to server caps; ``limits`` reports the effective values and why the
    view was truncated. Risk fields are stored assessments — nothing is scored in this request.
    """
    s = request.app.state.settings
    budget = graph_view.GraphBudget(
        max_nodes=min(max_nodes, s.graph_max_nodes),
        max_edges=s.graph_max_edges,
        max_formations=min(max_formations, s.graph_max_formations),
    )
    sid = parse_uuid(snapshot_id, "snapshot_id")
    bands = list(band) if band else None
    kinds = list(kind) if kind else None
    if mode == "local":
        if not account_id:
            raise Invalid("ACCOUNT_REQUIRED", "local mode requires account_id")
        return graph_view.local(session, sid, account_id, min(depth, s.graph_max_depth), budget, bands, kinds)
    return graph_view.overview(session, sid, budget, bands, kinds)


@router.get("/snapshots/{snapshot_id}/edge-transactions", response_model=schemas.TransactionPage, tags=["graph"])
def edge_transactions(
    snapshot_id: str,
    session: SessionDep,
    sender: str = Query(min_length=1, max_length=128),
    receiver: str = Query(min_length=1, max_length=128),
    currency: str = Query(pattern="^[A-Z]{3}$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Any:
    """The source transfers aggregated into one directed graph edge — same eligibility as the edge."""
    rows, total = graph_view.edge_transactions(
        session, parse_uuid(snapshot_id, "snapshot_id"), sender, receiver, currency, limit, offset
    )
    return {"items": [queries.tx_dict(t) for t in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/snapshots/{snapshot_id}/activity", response_model=schemas.Activity, tags=["graph"])
def activity(snapshot_id: str, session: SessionDep) -> Any:
    return queries.activity(session, parse_uuid(snapshot_id, "snapshot_id"))


@router.get("/snapshots/{snapshot_id}/accounts/{account_id}", response_model=schemas.AccountSummary, tags=["graph"])
def account(snapshot_id: str, account_id: str, session: SessionDep) -> Any:
    return queries.account_summary(session, parse_uuid(snapshot_id, "snapshot_id"), account_id)


@router.get("/snapshots/{snapshot_id}/transactions", response_model=schemas.TransactionPage, tags=["graph"])
def snapshot_transactions(
    snapshot_id: str,
    session: SessionDep,
    account_id: str | None = Query(None, max_length=128),
    counterparty_id: str | None = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Any:
    return queries.snapshot_transactions(
        session, parse_uuid(snapshot_id, "snapshot_id"), account_id, counterparty_id, limit, offset
    )


@router.get("/transactions/{transaction_id}", response_model=schemas.Transaction, tags=["graph"])
def transaction(transaction_id: str, session: SessionDep) -> Any:
    return queries.get_transaction(session, parse_uuid(transaction_id, "transaction_id"))
