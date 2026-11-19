"""Operator commands for analyst accounts. Passwords are never accepted as command-line arguments
(they would land in shell history and process listings): they are read from a TTY prompt, from
stdin (``--password-stdin``), or generated (``--generate``, printed once to stdout).

    python -m nexora.auth.cli create-user alice --display-name "Alice Analyst" --generate
    printf '%s' "$PW" | python -m nexora.auth.cli create-user alice --password-stdin
    python -m nexora.auth.cli set-password alice --generate      # also ends alice's sessions
    python -m nexora.auth.cli disable alice | enable alice | revoke-sessions alice
    python -m nexora.auth.cli hash-password --generate           # prints password + Argon2id hash
    python -m nexora.auth.cli bootstrap                           # see below

``bootstrap`` creates one account from NEXORA_BOOTSTRAP_USERNAME and NEXORA_BOOTSTRAP_PASSWORD_HASH
(an Argon2id hash, never a password) if that user does not exist yet; it is a no-op otherwise, and
when the variables are unset. It lets an operator provision the first analyst on a platform without
shell access to the container (Railway pre-deploy step), without the password ever reaching it.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexora.application.errors import AppError
from nexora.auth import passwords, service
from nexora.persistence import orm
from nexora.persistence.db import session_factory, session_scope
from nexora.settings import get_settings


def _generated() -> str:
    return secrets.token_urlsafe(18)  # 24 characters, 144 bits


def _read_password(args: argparse.Namespace) -> tuple[str, bool]:
    if args.generate:
        return _generated(), True
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\r\n"), False
    if not sys.stdin.isatty():
        raise SystemExit("refusing to read a password from a non-interactive stdin without --password-stdin")
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("passwords do not match")
    return first, False


def _add_password_source(p: argparse.ArgumentParser) -> None:
    src = p.add_mutually_exclusive_group()
    src.add_argument("--password-stdin", action="store_true", help="read the password from the first line of stdin")
    src.add_argument("--generate", action="store_true", help="generate a strong password and print it once")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m nexora.auth.cli", description="Manage NEXORA analyst accounts.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-user", help="create an analyst account")
    p.add_argument("username")
    p.add_argument("--display-name")
    _add_password_source(p)
    p = sub.add_parser("set-password", help="change a password and end all of the user's sessions")
    p.add_argument("username")
    _add_password_source(p)
    for name in ("disable", "enable", "revoke-sessions"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("list-users")
    p = sub.add_parser("hash-password", help="print an Argon2id hash for NEXORA_BOOTSTRAP_PASSWORD_HASH")
    _add_password_source(p)
    sub.add_parser("bootstrap", help="create the account named by NEXORA_BOOTSTRAP_* if it does not exist")
    args = parser.parse_args(argv)

    if args.command == "hash-password":
        password, generated = _read_password(args)
        if problem := passwords.password_problem(password):
            raise SystemExit(problem)
        if generated:
            print(f"password: {password}")
        print(passwords.hash_password(password))
        return 0

    settings = get_settings()
    factory = session_factory(settings.database_url)
    try:
        with session_scope(factory) as s:
            if args.command == "bootstrap":
                return _bootstrap(s)
            if args.command == "create-user":
                password, generated = _read_password(args)
                user = service.create_user(s, username=args.username, password=password, display_name=args.display_name)
                print(f"created user {user.username}")
                if generated:
                    print(f"password: {password}")
            elif args.command == "set-password":
                password, generated = _read_password(args)
                ended = service.set_password(s, username=args.username, password=password)
                print(f"password changed; {ended} session(s) ended")
                if generated:
                    print(f"password: {password}")
            elif args.command in ("disable", "enable"):
                ended = service.set_active(s, username=args.username, active=args.command == "enable")
                print(f"user {args.command}d; {ended} session(s) ended")
            elif args.command == "revoke-sessions":
                print(f"{service.revoke_sessions(s, username=args.username)} session(s) ended")
            elif args.command == "list-users":
                for u in s.scalars(select(orm.User).order_by(orm.User.username)):
                    state = "active" if u.is_active else "disabled"
                    print(f"{u.username}\t{state}\tlast sign-in {u.last_login_at or '-'}")
    except AppError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1
    return 0


def _bootstrap(s: Session) -> int:
    outcome = service.bootstrap_from_settings(s, get_settings())
    print(
        {
            "unset": "bootstrap: NEXORA_BOOTSTRAP_* not set; nothing to do",
            "exists": "bootstrap: user already exists; nothing changed",
            "created": "bootstrap: user created",
        }[outcome]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
