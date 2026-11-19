"""Sign-in, session validation, sign-out and account management.

Every failure that could tell an attacker whether an account exists produces the same result:
unknown user, wrong password and disabled account all return ``INVALID_CREDENTIALS`` after the same
Argon2 work, and throttling counts failures per *submitted name* whether or not it exists.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import math
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from nexora.application.errors import Conflict, Invalid, NotFound, TooManyRequests, Unauthorized
from nexora.auth import passwords, tokens
from nexora.persistence import orm
from nexora.settings import Settings

USERNAME_MIN, USERNAME_MAX = 3, 64
# last_seen_at is refreshed at most this often, so reads do not turn every request into a write.
_TOUCH_INTERVAL = dt.timedelta(seconds=60)
# Expired/revoked sessions and old sign-in attempts are deleted after this long.
_RETENTION = dt.timedelta(days=7)

INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
AUTH_REQUIRED = "AUTH_REQUIRED"


@dataclass(frozen=True)
class Principal:
    """The authenticated identity of a request, taken only from the validated server session."""

    user_id: uuid.UUID
    username: str
    display_name: str
    session_id: uuid.UUID
    session_expires_at: dt.datetime
    csrf_token: str


@dataclass(frozen=True)
class SignIn:
    principal: Principal
    token: str


def normalize_username(raw: str) -> str:
    return unicodedata.normalize("NFKC", raw).strip().casefold()


def username_problem(name: str) -> str | None:
    if not USERNAME_MIN <= len(name) <= USERNAME_MAX:
        return f"user name must be {USERNAME_MIN}-{USERNAME_MAX} characters"
    if not all(c.isalnum() or c in "._-@" for c in name):
        return "user name may contain letters, digits and . _ - @"
    return None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _username_digest(settings: Settings, name: str) -> str:
    # Keyed with the deployment's gateway secret where one exists, so a database dump does not reveal
    # submitted names (which are occasionally passwords typed into the wrong field).
    key = (settings.gateway_token or "nexora-local-unkeyed").encode()
    return hmac.new(key, name.encode("utf-8"), hashlib.sha256).hexdigest()


def _principal(user: orm.User, sess: orm.AuthSession, token: str) -> Principal:
    return Principal(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        session_id=sess.id,
        session_expires_at=sess.expires_at,
        csrf_token=tokens.csrf_token(token),
    )


def _audit(
    session: Session, *, actor: str, action: str, entity_id: str, request_id: str | None, **after: object
) -> None:
    session.add(
        orm.AuditEvent(
            actor=actor,
            action=action,
            entity_type="auth_session",
            entity_id=entity_id,
            before_json=None,
            after_json=dict(after) or None,
            reason=None,
            request_id=request_id,
        )
    )


# -- throttling ----------------------------------------------------------------------------------
def _check_throttle(session: Session, settings: Settings, digest: str, client: str, now: dt.datetime) -> None:
    window = dt.timedelta(minutes=settings.login_window_minutes)
    since = now - window
    # A successful sign-in starts a fresh count for that name.
    last_ok = session.scalar(
        select(func.max(orm.LoginAttempt.created_at)).where(
            orm.LoginAttempt.username_digest == digest, orm.LoginAttempt.succeeded.is_(True)
        )
    )
    user_since = max(since, last_ok) if last_ok else since
    scopes = (
        (orm.LoginAttempt.username_digest == digest, user_since, settings.login_max_failures_per_user),
        (orm.LoginAttempt.client == client, since, settings.login_max_failures_per_client),
    )
    for condition, start, limit in scopes:
        failures = (
            select(orm.LoginAttempt.created_at)
            .where(condition, orm.LoginAttempt.succeeded.is_(False), orm.LoginAttempt.created_at > start)
            .order_by(orm.LoginAttempt.created_at.desc())
            .limit(limit)
            .subquery()
        )
        count, oldest = session.execute(select(func.count(), func.min(failures.c.created_at))).one()
        if count >= limit and oldest is not None:
            retry = max(1, math.ceil((oldest + window - now).total_seconds()))
            raise TooManyRequests(
                "TOO_MANY_ATTEMPTS", "too many sign-in attempts; try again later", retry_after_seconds=retry
            )


def _prune(session: Session, now: dt.datetime) -> None:
    cutoff = now - _RETENTION
    session.execute(delete(orm.LoginAttempt).where(orm.LoginAttempt.created_at < cutoff))
    session.execute(
        delete(orm.AuthSession).where((orm.AuthSession.expires_at < cutoff) | (orm.AuthSession.revoked_at < cutoff))
    )


# -- sign-in / sign-out ---------------------------------------------------------------------------
def sign_in(
    session: Session,
    settings: Settings,
    *,
    username: str,
    password: str,
    client: str,
    previous_token: str | None,
    request_id: str | None,
) -> SignIn:
    """Verify credentials and open a new session.

    The throttle check and the attempt record run in the caller's transaction; a failed attempt is
    committed by the caller before the error response (see the auth route)."""
    now = _now()
    name = normalize_username(username)
    digest = _username_digest(settings, name)
    _check_throttle(session, settings, digest, client, now)

    user = session.scalar(select(orm.User).where(orm.User.username == name)) if name else None
    if user is not None and user.is_active:
        ok = passwords.verify_password(user.password_hash, password)
    else:
        passwords.burn_verification(password)
        ok = False
    session.add(orm.LoginAttempt(username_digest=digest, client=client, succeeded=ok))
    if not ok or user is None:
        raise Unauthorized(INVALID_CREDENTIALS, "invalid user name or password")

    # Session fixation: whatever session the browser presented is ended; a new random token is issued.
    if previous_token and tokens.well_formed(previous_token):
        _revoke_by_token(session, previous_token, now, "replaced_by_sign_in")
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    user.last_login_at = now
    token = tokens.new_session_token()
    sess = orm.AuthSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=tokens.token_digest(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + dt.timedelta(hours=settings.session_absolute_hours),
    )
    session.add(sess)
    _audit(session, actor=user.username, action="auth.sign_in", entity_id=str(sess.id), request_id=request_id)
    _prune(session, now)
    session.flush()
    return SignIn(principal=_principal(user, sess, token), token=token)


def _revoke_by_token(session: Session, token: str, now: dt.datetime, reason: str) -> orm.AuthSession | None:
    sess = session.scalar(
        select(orm.AuthSession).where(
            orm.AuthSession.token_hash == tokens.token_digest(token), orm.AuthSession.revoked_at.is_(None)
        )
    )
    if sess is not None:
        sess.revoked_at = now
        sess.revoked_reason = reason
    return sess


def sign_out(session: Session, principal: Principal, *, token: str, request_id: str | None) -> None:
    now = _now()
    _revoke_by_token(session, token, now, "signed_out")
    _audit(
        session,
        actor=principal.username,
        action="auth.sign_out",
        entity_id=str(principal.session_id),
        request_id=request_id,
    )


def authenticate(session: Session, settings: Settings, token: str | None) -> Principal | None:
    """Resolve a session cookie to a principal, or None for a missing, malformed, unknown, expired
    or revoked session, or a disabled account. All of these are treated identically by callers."""
    if not token or not tokens.well_formed(token):
        return None
    now = _now()
    row = session.execute(
        select(orm.AuthSession, orm.User)
        .join(orm.User, orm.User.id == orm.AuthSession.user_id)
        .where(orm.AuthSession.token_hash == tokens.token_digest(token))
    ).one_or_none()
    if row is None:
        return None
    sess, user = row
    idle = dt.timedelta(minutes=settings.session_idle_minutes)
    if sess.revoked_at is not None or sess.expires_at <= now or sess.last_seen_at + idle <= now or not user.is_active:
        return None
    if now - sess.last_seen_at >= _TOUCH_INTERVAL:
        session.execute(update(orm.AuthSession).where(orm.AuthSession.id == sess.id).values(last_seen_at=now))
    return _principal(user, sess, token)


# -- account management (operator CLI) ------------------------------------------------------------
def create_user(session: Session, *, username: str, password: str, display_name: str | None = None) -> orm.User:
    name = normalize_username(username)
    if problem := username_problem(name):
        raise Invalid("INVALID_USERNAME", problem)
    if problem := passwords.password_problem(password):
        raise Invalid("WEAK_PASSWORD", problem)
    return create_user_with_hash(
        session, username=name, password_hash=passwords.hash_password(password), display_name=display_name
    )


def create_user_with_hash(
    session: Session, *, username: str, password_hash: str, display_name: str | None = None
) -> orm.User:
    name = normalize_username(username)
    if problem := username_problem(name):
        raise Invalid("INVALID_USERNAME", problem)
    if not passwords.is_argon2id_hash(password_hash):
        raise Invalid("INVALID_HASH", "password hash must be an Argon2id PHC string")
    if session.scalar(select(orm.User.id).where(orm.User.username == name)) is not None:
        raise Conflict("USER_EXISTS", f"user {name!r} already exists")
    user = orm.User(
        id=uuid.uuid4(), username=name, display_name=(display_name or name).strip()[:120], password_hash=password_hash
    )
    session.add(user)
    session.add(
        orm.AuditEvent(
            actor="operator-cli",
            action="user.create",
            entity_type="user",
            entity_id=name,
            before_json=None,
            after_json={"username": name},
            reason=None,
            request_id=None,
        )
    )
    session.flush()
    return user


def _user(session: Session, username: str) -> orm.User:
    user = session.scalar(select(orm.User).where(orm.User.username == normalize_username(username)))
    if user is None:
        raise NotFound("USER_NOT_FOUND", "no such user")
    return user


def revoke_user_sessions(session: Session, user: orm.User, reason: str) -> int:
    result = session.execute(
        update(orm.AuthSession)
        .where(orm.AuthSession.user_id == user.id, orm.AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def set_password(session: Session, *, username: str, password: str) -> int:
    """Change a password and end every session of that user. Returns the number of sessions ended."""
    if problem := passwords.password_problem(password):
        raise Invalid("WEAK_PASSWORD", problem)
    user = _user(session, username)
    user.password_hash = passwords.hash_password(password)
    user.password_changed_at = _now()
    ended = revoke_user_sessions(session, user, "password_changed")
    session.add(
        orm.AuditEvent(
            actor="operator-cli",
            action="user.set_password",
            entity_type="user",
            entity_id=user.username,
            before_json=None,
            after_json={"sessions_revoked": ended},
            reason=None,
            request_id=None,
        )
    )
    return ended


def set_active(session: Session, *, username: str, active: bool) -> int:
    user = _user(session, username)
    user.is_active = active
    ended = 0 if active else revoke_user_sessions(session, user, "account_disabled")
    session.add(
        orm.AuditEvent(
            actor="operator-cli",
            action="user.enable" if active else "user.disable",
            entity_type="user",
            entity_id=user.username,
            before_json=None,
            after_json={"sessions_revoked": ended},
            reason=None,
            request_id=None,
        )
    )
    return ended


def revoke_sessions(session: Session, *, username: str) -> int:
    user = _user(session, username)
    ended = revoke_user_sessions(session, user, "revoked_by_operator")
    session.add(
        orm.AuditEvent(
            actor="operator-cli",
            action="user.revoke_sessions",
            entity_type="user",
            entity_id=user.username,
            before_json=None,
            after_json={"sessions_revoked": ended},
            reason=None,
            request_id=None,
        )
    )
    return ended


def bootstrap_from_settings(session: Session, settings: Settings) -> str:
    """Create the account named by NEXORA_BOOTSTRAP_USERNAME / _PASSWORD_HASH if it does not exist.

    Idempotent; returns "unset", "exists" or "created". Raises Invalid for a half-set or non-Argon2id
    configuration (never a plaintext password)."""
    name, hashed = settings.bootstrap_username.strip(), settings.bootstrap_password_hash.strip()
    if not name and not hashed:
        return "unset"
    if not name or not hashed:
        raise Invalid("BOOTSTRAP_INCOMPLETE", "set both NEXORA_BOOTSTRAP_USERNAME and NEXORA_BOOTSTRAP_PASSWORD_HASH")
    if session.scalar(select(orm.User.id).where(orm.User.username == normalize_username(name))) is not None:
        return "exists"
    create_user_with_hash(session, username=name, password_hash=hashed)
    return "created"
