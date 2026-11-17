"""Human-in-the-loop case lifecycle (spec §15).

Every decision and its audit event commit in the same transaction. Optimistic
concurrency (``expected_version``) prevents lost updates. No transition triggers any
external banking action — decisions are recorded analyst judgements only.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nexora.application.errors import Conflict, Invalid, NotFound
from nexora.persistence import orm

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
    alert = session.get(orm.Alert, alert_id)
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
    case = session.execute(select(orm.Case).where(orm.Case.id == case_id).with_for_update()).scalar_one_or_none()
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
    case = session.get(orm.Case, case_id)
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
