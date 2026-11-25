"""Request identity boundary. A verifier must authenticate the token before issuing a principal."""

from __future__ import annotations

import re
from typing import Annotated, Literal, Protocol

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints, TypeAdapter

from nexora.domain.ids import sha256_hex

Reference = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:@-]{1,128}$")]
Role = Literal["customer", "analyst", "reviewer", "administrator", "service"]


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: Reference
    tenant: Reference
    role: Role
    customer_ref: Reference | None = None


class IdentityVerifier(Protocol):
    def verify(self, token: str) -> Principal | None: ...


class LocalTokenVerifier:
    """Offline sandbox identities provisioned using precomputed digests of random tokens."""

    def __init__(self, identities: dict[str, Principal]):
        if any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in identities):
            raise ValueError("local identity entries must use SHA-256 digests")
        self.identities = dict(identities)

    @classmethod
    def from_json(cls, provisioned: str) -> LocalTokenVerifier:
        try:
            return cls(TypeAdapter(dict[str, Principal]).validate_json(provisioned))
        except ValueError:
            raise ValueError("local identity configuration is invalid") from None

    def verify(self, token: str) -> Principal | None:
        return self.identities.get(sha256_hex(token))


def authenticate(request: Request, authorization: Annotated[str | None, Header()] = None) -> Principal:
    verifier: IdentityVerifier | None = request.app.state.identity_verifier
    scheme, _, token = (authorization or "").partition(" ")
    if verifier is not None and scheme.lower() == "bearer" and 32 <= len(token) <= 8192:
        principal = verifier.verify(token)
        if principal is not None:
            return principal
    raise HTTPException(status_code=401, detail="authentication required", headers={"WWW-Authenticate": "Bearer"})


PrincipalDep = Annotated[Principal, Depends(authenticate)]
