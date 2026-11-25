"""Human-in-the-loop case lifecycle (spec §15).

Every decision and its audit event commit in the same transaction. Optimistic
concurrency (``expected_version``) prevents lost updates. No transition triggers any
external banking action — decisions are recorded analyst judgements only.
"""

from __future__ import annotations

import datetime as dt
import hmac
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexora.application.errors import Conflict, Invalid, NotFound
from nexora.persistence import orm
from nexora.persistence.access import case_filter, dataset_filter

TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"investigating"}),
    "investigating": frozenset({"escalated", "dismissed", "closed"}),
    "escalated": frozenset({"closed"}),
    "dismissed": frozenset({"closed"}),
    "closed": frozenset({"reopened"}),
    "reopened": frozenset({"investigating"}),
}
REASON_REQUIRED = frozenset({"escalated", "dismissed", "closed", "reopened"})
DECISIONS = frozenset({"escalated", "dismissed"})
MAX_REASON = 2000
MAX_NOTE = 4000


def _audit(
    session: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    reason: str | None,
    request_id: str | None,
) -> None:
    session.add(
        orm.AuditEvent(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=before,
            after_json=after,
            reason=reason,
            request_id=request_id,
        )
    )


def _state(c: orm.Case) -> dict[str, Any]:
    return {"status": c.status, "version": c.version, "decision": c.decision, "assigned_to": c.assigned_to}


def open_case(session: Session, *, alert_id: uuid.UUID, actor: str, request_id: str | None) -> tuple[orm.Case, bool]:
    """Open a case for an alert. Idempotent: returns ``(case, created)``."""
    alert = session.scalar(
        select(orm.Alert).where(orm.Alert.id == alert_id, dataset_filter(session, orm.Alert.dataset_id))
    )
    if alert is None:
        raise NotFound("ALERT_NOT_FOUND", "alert does not exist")
    existing = session.execute(select(orm.Case).where(orm.Case.alert_id == alert_id)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    formation = session.get(orm.Formation, alert.formation_id)
    title = f"{formation.kind}:{formation.subject_account_id}" if formation else f"alert:{alert_id}"
    case = orm.Case(id=uuid.uuid4(), alert_id=alert_id, title=title, status="new", assigned_to=actor, version=1)
    try:
        with session.begin_nested():
            session.add(case)
            session.flush()
    except IntegrityError:
        # A concurrent request opened the case first; return that one.
        return session.execute(select(orm.Case).where(orm.Case.alert_id == alert_id)).scalar_one(), False
    alert.status = "in_case"
    _audit(
        session,
        actor=actor,
        action="case.opened",
        entity_type="case",
        entity_id=str(case.id),
        before=None,
        after={**_state(case), "alert_id": str(alert_id)},
        reason=None,
        request_id=request_id,
    )
    return case, True


def transition(
    session: Session,
    *,
    case_id: uuid.UUID,
    to_status: str,
    expected_version: int,
    reason: str | None,
    actor: str,
    request_id: str | None,
) -> orm.Case:
    case = session.execute(
        select(orm.Case).where(orm.Case.id == case_id, case_filter(session)).with_for_update()
    ).scalar_one_or_none()
    if case is None:
        raise NotFound("CASE_NOT_FOUND", "case does not exist")
    if case.version != expected_version:
        raise Conflict(
            "CASE_VERSION_CONFLICT",
            "case was modified by someone else; reload and retry",
            {"expected_version": expected_version, "current_version": case.version},
        )
    if to_status not in TRANSITIONS.get(case.status, frozenset()):
        raise Invalid(
            "CASE_TRANSITION_NOT_ALLOWED",
            f"cannot move case from {case.status} to {to_status}",
            {
                "from": case.status,
                "to": to_status,
                "allowed": sorted(TRANSITIONS.get(case.status, frozenset())),
            },
        )
    clean_reason = (reason or "").strip()
    if to_status in REASON_REQUIRED and not clean_reason:
        raise Invalid("CASE_REASON_REQUIRED", f"a reason is required to move a case to {to_status}")
    if len(clean_reason) > MAX_REASON:
        raise Invalid("CASE_REASON_TOO_LONG", f"reason must be at most {MAX_REASON} characters")

    before = _state(case)
    values: dict[str, Any] = {"status": to_status, "version": case.version + 1}
    if to_status in DECISIONS:
        values.update(decision=to_status, decision_reason=clean_reason)
    if to_status == "closed":
        values["closed_at"] = dt.datetime.now(dt.UTC)
    if to_status == "reopened":
        values["closed_at"] = None
    result = session.execute(
        update(orm.Case)
        .where(orm.Case.id == case_id, orm.Case.version == expected_version)
        .values(**values)
        .returning(orm.Case.id)
    ).first()
    if result is None:  # defensive: row lock should make this unreachable
        raise Conflict("CASE_VERSION_CONFLICT", "case was modified concurrently")
    session.refresh(case)
    alert = session.get(orm.Alert, case.alert_id)
    if alert is not None:
        alert.status = "closed" if to_status == "closed" else "in_case"
    _audit(
        session,
        actor=actor,
        action=f"case.{to_status}",
        entity_type="case",
        entity_id=str(case_id),
        before=before,
        after=_state(case),
        reason=clean_reason or None,
        request_id=request_id,
    )
    return case


def add_note(session: Session, *, case_id: uuid.UUID, body: str, actor: str, request_id: str | None) -> orm.CaseNote:
    case = session.scalar(select(orm.Case).where(orm.Case.id == case_id, case_filter(session)))
    if case is None:
        raise NotFound("CASE_NOT_FOUND", "case does not exist")
    text_body = body.strip()
    if not text_body:
        raise Invalid("NOTE_EMPTY", "note must not be empty")
    if len(text_body) > MAX_NOTE:
        raise Invalid("NOTE_TOO_LONG", f"note must be at most {MAX_NOTE} characters")
    note = orm.CaseNote(id=uuid.uuid4(), case_id=case_id, author=actor, body=text_body)
    session.add(note)
    session.flush()
    _audit(
        session,
        actor=actor,
        action="case.note_added",
        entity_type="case",
        entity_id=str(case_id),
        before=None,
        after={"note_id": str(note.id), "length": len(text_body)},
        reason=None,
        request_id=request_id,
    )
    return note


FEEDBACK_ACTION = "case.feedback_reviewed"


def _feedback_target(session: Session, case_id: uuid.UUID, *, lock: bool = False) -> tuple[orm.Case, orm.Alert]:
    stmt = (
        select(orm.Case, orm.Alert)
        .join(orm.Alert, orm.Alert.id == orm.Case.alert_id)
        .where(orm.Case.id == case_id, case_filter(session))
    )
    if lock:
        stmt = stmt.with_for_update(of=(orm.Case, orm.Alert))
    row = session.execute(stmt).one_or_none()
    if row is None:
        raise NotFound("CASE_NOT_FOUND", "case does not exist")
    return row[0], row[1]


def _latest_feedback(session: Session, case_id: uuid.UUID) -> orm.AuditEvent | None:
    return session.scalar(
        select(orm.AuditEvent)
        .where(
            orm.AuditEvent.entity_type == "case",
            orm.AuditEvent.entity_id == str(case_id),
            orm.AuditEvent.action == FEEDBACK_ACTION,
        )
        .order_by(orm.AuditEvent.id.desc())
        .limit(1)
    )


def review_feedback(
    session: Session,
    *,
    case_id: uuid.UUID,
    expected_case_version: int,
    expected_alert_revision: int,
    expected_review_id: int | None,
    outcome: str,
    reason: str,
    reviewer: str,
    request_id: str,
) -> orm.AuditEvent:
    case, alert = _feedback_target(session, case_id, lock=True)
    previous = _latest_feedback(session, case.id)
    previous_id = previous.id if previous else None
    if (case.version, alert.revision, previous_id) != (
        expected_case_version,
        expected_alert_revision,
        expected_review_id,
    ):
        raise Conflict("FEEDBACK_VERSION_CONFLICT", "case, alert or review changed; reload the evidence")
    if case.status not in {"escalated", "dismissed", "closed"} or case.decision not in DECISIONS:
        raise Conflict("FEEDBACK_DISPOSITION_REQUIRED", "a completed case disposition is required")
    author = session.scalar(
        select(orm.AuditEvent.actor)
        .where(
            orm.AuditEvent.entity_type == "case",
            orm.AuditEvent.entity_id == str(case_id),
            orm.AuditEvent.action == f"case.{case.decision}",
        )
        .order_by(orm.AuditEvent.id.desc())
        .limit(1)
    )
    if author is None or author == reviewer:
        raise Conflict("FEEDBACK_INDEPENDENT_REVIEW_REQUIRED", "feedback requires an independent reviewer")
    if not reason.strip():
        raise Invalid("FEEDBACK_REASON_REQUIRED", "feedback requires a review reason")
    snapshot = session.get(orm.GraphSnapshot, alert.snapshot_id)
    assert snapshot is not None
    _audit(
        session,
        actor=reviewer,
        action=FEEDBACK_ACTION,
        entity_type="case",
        entity_id=str(case_id),
        before={"supersedes_review_id": previous_id},
        after={
            "case_version": case.version,
            "alert_revision": alert.revision,
            "snapshot_id": str(snapshot.id),
            "evidence_digest": alert.evidence_digest,
            "policy_version": snapshot.policy_version,
            "outcome": outcome,
        },
        reason=reason.strip(),
        request_id=request_id,
    )
    session.flush()
    event = _latest_feedback(session, case.id)
    assert event is not None
    return event


def feedback_label(session: Session, case_id: uuid.UUID, secret: str) -> dict[str, Any]:
    case, alert = _feedback_target(session, case_id)
    event = _latest_feedback(session, case.id)
    if event is None or not event.after_json:
        raise NotFound("FEEDBACK_NOT_REVIEWED", "case has no reviewed feedback")
    review = event.after_json
    if (review["case_version"], review["alert_revision"]) != (case.version, alert.revision):
        raise Conflict("FEEDBACK_OUTDATED", "the review no longer matches the case and alert")
    if review["outcome"] == "insufficient_evidence":
        raise Conflict("FEEDBACK_INSUFFICIENT", "the reviewed outcome is inconclusive")
    opaque = hmac.digest(
        secret.encode(), f"nexora-feedback-v1:{session.info['tenant']}:{case.id}".encode(), "sha256"
    ).hex()
    return {
        "version": "feedback-v1",
        "sample_ref": opaque,
        "label": review["outcome"],
        "quality": "independently_reviewed",
        "policy_version": review["policy_version"],
    }
