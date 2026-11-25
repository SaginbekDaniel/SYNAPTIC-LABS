"""Authenticated preflight and durable acknowledgements for simulated transfers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Request, Response
from pydantic import AwareDatetime, StringConstraints
from sqlalchemy import select

from nexora.api.deps import SessionDep
from nexora.api.identity import PrincipalDep, Reference
from nexora.api.routes.transfer_checks import CUSTOMER_MESSAGES, AnalystAccessRequired
from nexora.api.schemas import Model
from nexora.application.errors import Conflict
from nexora.application.transfer_protection import (
    Action,
    Coverage,
    Decision,
    Reason,
    RecipientProfile,
    RiskBand,
    TransferIntent,
)
from nexora.application.transfer_sandbox import (
    REVIEW_ACTIONS,
    SandboxAction,
    SandboxStatus,
    create_assessment,
    scoped_assessment,
)
from nexora.domain.money import parse_amount_minor
from nexora.persistence.orm import TransferActionEvent, TransferAssessment

router = APIRouter(prefix="/api/v1/sandbox/transfers", tags=["transfer sandbox"])
CUSTOMER_ROLES = frozenset({"customer", "service"})
ANALYST_ROLES = frozenset({"analyst", "reviewer", "administrator"})
REVIEWER_ROLES = frozenset({"reviewer", "administrator"})


class SandboxIntentRequest(Model):
    intent_id: uuid.UUID
    beneficiary: Reference
    amount_minor: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,37}$")]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    requested_at: AwareDatetime
    channel: Literal["web", "mobile", "service"] = "web"
    supersedes_assessment_id: uuid.UUID | None = None


class SandboxAssessmentResponse(Model):
    assessment_id: uuid.UUID
    intent_id: uuid.UUID
    decision: Decision
    risk_band: RiskBand
    coverage: Coverage
    reason_codes: list[Reason]
    recommended_actions: list[Action]
    policy_version: str
    snapshot_id: str | None
    customer_message: str
    status: SandboxStatus
    assessed_at: datetime
    simulation: Literal[True] = True


class SandboxActionRequest(Model):
    action_id: uuid.UUID
    action: SandboxAction


class SandboxAcknowledgement(Model):
    assessment_id: uuid.UUID
    action_id: uuid.UUID
    action: SandboxAction
    from_status: SandboxStatus
    to_status: SandboxStatus
    acknowledged_at: datetime
    simulation: Literal[True] = True


class SandboxEvidenceResponse(Model):
    assessment: SandboxAssessmentResponse
    profile: RecipientProfile | None


def _summary(row: TransferAssessment) -> SandboxAssessmentResponse:
    return SandboxAssessmentResponse(
        assessment_id=row.id,
        intent_id=row.intent_id,
        status=cast(SandboxStatus, row.status),
        assessed_at=row.created_at,
        **{"customer_message": CUSTOMER_MESSAGES[row.assessment["decision"]], **row.assessment},
    )


@router.post("", status_code=201)
def submit(
    body: SandboxIntentRequest, request: Request, response: Response, principal: PrincipalDep, session: SessionDep
) -> SandboxAssessmentResponse:
    if principal.role not in CUSTOMER_ROLES or principal.customer_ref is None:
        raise AnalystAccessRequired("SANDBOX_ROLE_REQUIRED", "transfer initiator authorization is required")
    if body.supersedes_assessment_id is not None:
        previous = scoped_assessment(session, body.supersedes_assessment_id, principal.tenant, owner=principal.subject)
        if previous.status not in {"UNAVAILABLE", "CANCELLED"}:
            raise Conflict("SANDBOX_RETRY_UNAVAILABLE", "the previous assessment cannot be retried")
        if previous.intent_id == body.intent_id:
            raise Conflict("SANDBOX_RETRY_REQUIRES_NEW_INTENT", "retry requires a new intent identifier")
    payload = body.model_dump(mode="json") | {"customer_ref": principal.customer_ref}
    intent = TransferIntent(
        str(body.intent_id),
        principal.customer_ref,
        body.beneficiary,
        body.requested_at,
        parse_amount_minor(body.amount_minor),
        body.currency,
    )
    service = request.app.state.transfer_demo
    response.headers["Cache-Control"] = "no-store"
    return _summary(
        create_assessment(
            session,
            tenant=principal.tenant,
            owner=principal.subject,
            intent_id=body.intent_id,
            payload=payload,
            intent=intent,
            policy=service.policy if service.enabled else None,
            adapter=request.app.state.beneficiary_adapter,
            customer_messages=CUSTOMER_MESSAGES,
        )
    )


@router.get("/{assessment_id}")
def get_assessment(
    assessment_id: uuid.UUID, response: Response, principal: PrincipalDep, session: SessionDep
) -> SandboxAssessmentResponse:
    owner = None if principal.role in ANALYST_ROLES else principal.subject
    response.headers["Cache-Control"] = "no-store"
    return _summary(scoped_assessment(session, assessment_id, principal.tenant, owner=owner))


@router.get("/{assessment_id}/evidence")
def get_evidence(
    assessment_id: uuid.UUID, response: Response, principal: PrincipalDep, session: SessionDep
) -> SandboxEvidenceResponse:
    if principal.role not in ANALYST_ROLES:
        raise AnalystAccessRequired("SANDBOX_ANALYST_REQUIRED", "analyst authorization is required")
    row = scoped_assessment(session, assessment_id, principal.tenant)
    response.headers["Cache-Control"] = "no-store"
    return SandboxEvidenceResponse(
        assessment=_summary(row),
        profile=RecipientProfile.model_validate(row.evidence) if row.evidence else None,
    )


@router.post("/{assessment_id}/actions")
def perform_action(
    assessment_id: uuid.UUID,
    body: SandboxActionRequest,
    request: Request,
    response: Response,
    principal: PrincipalDep,
    session: SessionDep,
) -> SandboxAcknowledgement:
    review = body.action in REVIEW_ACTIONS
    allowed_roles = REVIEWER_ROLES if review else CUSTOMER_ROLES
    if principal.role not in allowed_roles:
        raise AnalystAccessRequired("SANDBOX_ROLE_REQUIRED", "authorization is required for this sandbox action")
    row = scoped_assessment(
        session,
        assessment_id,
        principal.tenant,
        owner=None if review else principal.subject,
        lock=True,
    )
    event = request.app.state.payment_adapter.apply(
        session,
        row,
        actor=principal.subject,
        action_id=body.action_id,
        action=body.action,
    )
    response.headers["Cache-Control"] = "no-store"
    return SandboxAcknowledgement(
        assessment_id=row.id,
        action_id=event.action_id,
        action=cast(SandboxAction, event.action),
        from_status=cast(SandboxStatus, event.from_status),
        to_status=cast(SandboxStatus, event.to_status),
        acknowledged_at=event.created_at,
    )


@router.get("/{assessment_id}/actions")
def list_actions(
    assessment_id: uuid.UUID, response: Response, principal: PrincipalDep, session: SessionDep
) -> list[SandboxAcknowledgement]:
    owner = None if principal.role in ANALYST_ROLES else principal.subject
    row = scoped_assessment(session, assessment_id, principal.tenant, owner=owner)
    response.headers["Cache-Control"] = "no-store"
    events = session.scalars(
        select(TransferActionEvent)
        .where(TransferActionEvent.assessment_id == row.id)
        .order_by(
            TransferActionEvent.created_at,
            TransferActionEvent.action_id,
        )
    )
    return [
        SandboxAcknowledgement(
            assessment_id=row.id,
            action_id=event.action_id,
            action=cast(SandboxAction, event.action),
            from_status=cast(SandboxStatus, event.from_status),
            to_status=cast(SandboxStatus, event.to_status),
            acknowledged_at=event.created_at,
        )
        for event in events
    ]
