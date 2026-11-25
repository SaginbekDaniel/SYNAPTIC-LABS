from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from nexora.api import schemas
from nexora.api.deps import SessionDep, actor, parse_uuid, request_id, require_case_reviewer
from nexora.application import case_service, queries

router = APIRouter(prefix="/api/v1", tags=["cases"])
ActorDep = Annotated[str, Depends(actor)]
RequestIdDep = Annotated[str, Depends(request_id)]


@router.post("/cases", response_model=schemas.Case, status_code=201, responses={200: {"model": schemas.Case}})
def open_case(
    body: schemas.OpenCaseRequest, response: Response, session: SessionDep, who: ActorDep, rid: RequestIdDep
) -> Any:
    case, created = case_service.open_case(
        session, alert_id=parse_uuid(body.alert_id, "alert_id"), actor=who, request_id=rid
    )
    session.flush()
    if not created:
        response.status_code = 200
    return queries.case_dict(session, case)


@router.get("/cases", response_model=schemas.CasePage)
def list_cases(
    session: SessionDep,
    dataset_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Any:
    return queries.list_cases(
        session,
        dataset_id=parse_uuid(dataset_id, "dataset_id") if dataset_id else None,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/cases/{case_id}", response_model=schemas.Case)
def get_case(case_id: str, session: SessionDep) -> Any:
    return queries.get_case(session, parse_uuid(case_id, "case_id"))


@router.post("/cases/{case_id}/decisions", response_model=schemas.Case)
def decide(
    case_id: str, body: schemas.DecisionRequest, request: Request, session: SessionDep, who: ActorDep, rid: RequestIdDep
) -> Any:
    if body.to_status != "investigating":
        require_case_reviewer(request)
    case = case_service.transition(
        session,
        case_id=parse_uuid(case_id, "case_id"),
        to_status=body.to_status,
        expected_version=body.expected_version,
        reason=body.reason,
        actor=who,
        request_id=rid,
    )
    session.flush()
    return queries.case_dict(session, case)


@router.post("/cases/{case_id}/notes", response_model=schemas.Case, status_code=201)
def add_note(case_id: str, body: schemas.NoteRequest, session: SessionDep, who: ActorDep, rid: RequestIdDep) -> Any:
    cid = parse_uuid(case_id, "case_id")
    case_service.add_note(session, case_id=cid, body=body.body, actor=who, request_id=rid)
    session.flush()
    return queries.get_case(session, cid)


@router.get("/cases/{case_id}/audit", response_model=list[schemas.AuditEvent])
def audit(case_id: str, session: SessionDep) -> Any:
    return queries.case_audit(session, parse_uuid(case_id, "case_id"))


def _require_verified_reviewer(request: Request) -> None:
    if getattr(request.state, "analytics_principal", None) is None:
        raise HTTPException(403, "verified reviewer authorization required")
    require_case_reviewer(request)


@router.post("/cases/{case_id}/feedback", response_model=schemas.FeedbackReceipt, status_code=201)
def review_feedback(
    case_id: str, body: schemas.FeedbackReview, request: Request, session: SessionDep, who: ActorDep, rid: RequestIdDep
) -> Any:
    _require_verified_reviewer(request)
    event = case_service.review_feedback(
        session, case_id=parse_uuid(case_id, "case_id"), reviewer=who, request_id=rid, **body.model_dump()
    )
    return {"review_id": event.id, "created_at": event.created_at}


@router.get("/cases/{case_id}/feedback-label", response_model=schemas.FeedbackLabel)
def feedback_label(case_id: str, request: Request, session: SessionDep) -> Any:
    _require_verified_reviewer(request)
    secret = request.app.state.settings.feedback_export_key.get_secret_value()
    if len(secret) < 32:
        raise HTTPException(503, "feedback label export is not provisioned")
    return case_service.feedback_label(session, parse_uuid(case_id, "case_id"), secret)
