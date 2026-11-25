"""Point-in-time sandbox assessment and payment acknowledgement services."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nexora.application.errors import Conflict, NotFound
from nexora.application.transfer_protection import Decision, Failure, Policy, RecipientProfile, TransferIntent, assess
from nexora.domain.ids import canonical_json, sha256_hex
from nexora.persistence.orm import TransferActionEvent, TransferAssessment

SandboxAction = Literal["CONFIRM", "CANCEL", "VERIFY_STEP_UP", "HOLD_FOR_REVIEW", "APPROVE_REVIEW"]
SandboxStatus = Literal[
    "READY",
    "AWAITING_CONFIRMATION",
    "STEP_UP_REQUIRED",
    "IN_REVIEW",
    "UNAVAILABLE",
    "SIMULATED_COMPLETED",
    "CANCELLED",
]
INITIAL_STATUS = {
    "ALLOW": "READY",
    "WARN": "AWAITING_CONFIRMATION",
    "STEP_UP": "STEP_UP_REQUIRED",
    "LIMITED_SIGNAL": "IN_REVIEW",
    "UNAVAILABLE": "UNAVAILABLE",
}
REVIEW_ACTIONS = frozenset({"VERIFY_STEP_UP", "HOLD_FOR_REVIEW", "APPROVE_REVIEW"})
TRANSITIONS: dict[tuple[str, SandboxAction], SandboxStatus] = {
    ("READY", "CONFIRM"): "SIMULATED_COMPLETED",
    ("AWAITING_CONFIRMATION", "CONFIRM"): "SIMULATED_COMPLETED",
    ("STEP_UP_REQUIRED", "VERIFY_STEP_UP"): "READY",
    ("STEP_UP_REQUIRED", "HOLD_FOR_REVIEW"): "IN_REVIEW",
    ("AWAITING_CONFIRMATION", "HOLD_FOR_REVIEW"): "IN_REVIEW",
    ("IN_REVIEW", "APPROVE_REVIEW"): "READY",
    ("READY", "CANCEL"): "CANCELLED",
    ("AWAITING_CONFIRMATION", "CANCEL"): "CANCELLED",
    ("STEP_UP_REQUIRED", "CANCEL"): "CANCELLED",
    ("IN_REVIEW", "CANCEL"): "CANCELLED",
    ("UNAVAILABLE", "CANCEL"): "CANCELLED",
}


class BeneficiaryAdapter(Protocol):
    def lookup(self, intent: TransferIntent) -> tuple[RecipientProfile | None, Failure | None]: ...


@dataclass(frozen=True)
class FixtureBeneficiaryAdapter:
    profiles: tuple[RecipientProfile, ...]
    timeout_recipients: frozenset[str] = frozenset()
    available: bool = True

    @classmethod
    def from_profiles(
        cls, profiles: Iterable[RecipientProfile], *, graph_config_sha256: str, available: bool
    ) -> FixtureBeneficiaryAdapter:
        versioned = tuple(
            sorted(
                (profile for profile in profiles if profile.graph_config_sha256 == graph_config_sha256),
                key=lambda profile: (profile.as_of, profile.snapshot_id),
                reverse=True,
            )
        )
        return cls(versioned, frozenset({"demo-timeout"}), available)

    def lookup(self, intent: TransferIntent) -> tuple[RecipientProfile | None, Failure | None]:
        if not self.available:
            return None, "DEPENDENCY_FAILURE"
        if intent.recipient in self.timeout_recipients:
            return None, "TIMEOUT"
        profile = next(
            (
                candidate
                for candidate in self.profiles
                if (candidate.sender, candidate.recipient, candidate.currency)
                == (intent.sender, intent.recipient, intent.currency)
                and candidate.as_of <= intent.as_of
            ),
            None,
        )
        return profile, None


class SandboxPaymentAdapter:
    """Local state machine. Every acknowledgement is written in the assessment transaction."""

    def apply(
        self, session: Session, row: TransferAssessment, *, actor: str, action_id: uuid.UUID, action: SandboxAction
    ) -> TransferActionEvent:
        existing = session.get(TransferActionEvent, (row.id, action_id))
        if existing is not None:
            if existing.action != action or existing.actor != actor:
                raise Conflict("SANDBOX_ACTION_CONFLICT", "action identifier belongs to different input")
            return existing
        destination = TRANSITIONS.get((row.status, action))
        if destination is None:
            raise Conflict("SANDBOX_TRANSITION_INVALID", "sandbox action is unavailable in the current state")
        event = TransferActionEvent(
            assessment_id=row.id,
            action_id=action_id,
            actor=actor,
            action=action,
            from_status=row.status,
            to_status=destination,
        )
        row.status = destination
        session.add(event)
        session.flush()
        return event


def scoped_assessment(
    session: Session, assessment_id: uuid.UUID, tenant: str, *, owner: str | None = None, lock: bool = False
) -> TransferAssessment:
    stmt = select(TransferAssessment).where(TransferAssessment.id == assessment_id, TransferAssessment.tenant == tenant)
    if owner is not None:
        stmt = stmt.where(TransferAssessment.owner == owner)
    if lock:
        stmt = stmt.with_for_update()
    row = session.scalar(stmt)
    if row is None:
        raise NotFound("SANDBOX_ASSESSMENT_NOT_FOUND", "sandbox assessment was not found")
    return row


def create_assessment(
    session: Session,
    *,
    tenant: str,
    owner: str,
    intent_id: uuid.UUID,
    payload: dict,
    intent: TransferIntent,
    policy: Policy | None,
    adapter: BeneficiaryAdapter,
    customer_messages: dict[Decision, str],
) -> TransferAssessment:
    digest = sha256_hex(canonical_json(payload))
    existing = select(TransferAssessment).where(
        TransferAssessment.tenant == tenant,
        TransferAssessment.owner == owner,
        TransferAssessment.intent_id == intent_id,
    )
    row = session.scalar(existing)
    if row is None:
        try:
            profile, failure = adapter.lookup(intent)
        except TimeoutError:
            profile, failure = None, "TIMEOUT"
        if policy is None:
            failure = "DEPENDENCY_FAILURE"
        effective_policy = policy or Policy(version="unavailable", warn_with_confirmed_report_alone=False)
        result = assess(intent, profile, effective_policy, failure=failure)
        statement = (
            insert(TransferAssessment)
            .values(
                id=uuid.uuid4(),
                tenant=tenant,
                owner=owner,
                intent_id=intent_id,
                request_sha256=digest,
                intent=payload,
                assessment={
                    "decision": result.decision,
                    "customer_message": customer_messages[result.decision],
                    "risk_band": result.risk_band,
                    "coverage": result.coverage,
                    "reason_codes": list(result.reason_codes),
                    "policy_version": result.policy_version,
                    "snapshot_id": result.snapshot_id,
                    "recommended_actions": list(result.recommended_actions),
                },
                evidence=profile.model_dump(mode="json") if profile is not None and result.snapshot_id else None,
                status=INITIAL_STATUS[result.decision],
            )
            .on_conflict_do_nothing(constraint="uq_transfer_intent_scope")
            .returning(TransferAssessment)
        )
        row = session.scalar(statement) or session.scalars(existing).one()
    if row.request_sha256 != digest:
        raise Conflict("SANDBOX_INTENT_CONFLICT", "intent identifier belongs to different input")
    return row
