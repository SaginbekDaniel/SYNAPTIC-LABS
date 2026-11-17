from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response

from nexora.api import schemas
from nexora.api.deps import SessionDep, actor, parse_uuid
from nexora.application import analysis_service, queries
from nexora.application.errors import NotFound
from nexora.persistence import orm

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analysis/jobs", response_model=schemas.Job, status_code=202)
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
