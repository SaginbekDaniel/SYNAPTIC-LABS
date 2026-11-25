"""Account roles (backlog B-011, finding H-09).

Roles are ordered; each includes everything the roles before it may do:

* ``viewer``  - reads everything a signed-in user can read; changes nothing (except ending their own session).
* ``analyst`` - additionally generates synthetic datasets, runs analyses and works cases. The default:
  every account that existed before roles keeps exactly its previous permissions.
* ``admin``   - additionally imports CSV data when the deployment allows it (decision D-11). Account and
  role management stays with the operator CLI; nothing over HTTP changes a role.

Roles are global. Who may see *which* dataset is a separate question (B-019, decision D-3).
"""

from __future__ import annotations

from typing import Literal, get_args

Role = Literal["viewer", "analyst", "admin"]
ROLES: tuple[Role, ...] = get_args(Role)
DEFAULT_ROLE: Role = "analyst"


def is_role(value: str) -> bool:
    return value in ROLES


def allows(role: str, minimum: Role) -> bool:
    """True when ``role`` may do what ``minimum`` may. An unknown role is allowed nothing (fail closed)."""
    return is_role(role) and ROLES.index(role) >= ROLES.index(minimum)
