from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from nexora.api import schemas
from nexora.api.deps import get_session, parse_uuid
from nexora.application import queries

router = APIRouter(prefix="/api/v1", tags=["alerts"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/alerts", response_model=schemas.AlertPage)
def list_alerts(
    session: SessionDep,
    dataset_id: str | None = None,
    band: Annotated[list[schemas.Band] | None, Query()] = None,
    status: str | None = Query(None, pattern="^(open|in_case|closed)$"),
    kind: str | None = Query(None, pattern="^(funnel|chain|fanout|cycle)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Any:
    return queries.list_alerts(
        session,
        dataset_id=parse_uuid(dataset_id, "dataset_id") if dataset_id else None,
        bands=list(band) if band else None,
        status=status,
        kind=kind,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts/{alert_id}", response_model=schemas.AlertDetail)
def get_alert(alert_id: str, session: SessionDep) -> Any:
    return queries.alert_detail(session, parse_uuid(alert_id, "alert_id"))


@router.get("/alerts/{alert_id}/evidence", response_model=schemas.EvidenceChain)
def get_alert_evidence(alert_id: str, session: SessionDep) -> Any:
    return queries.alert_evidence_chain(session, parse_uuid(alert_id, "alert_id"))
