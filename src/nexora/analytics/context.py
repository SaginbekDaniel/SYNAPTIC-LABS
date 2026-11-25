"""Transaction-linked context from a trusted, point-in-time registry."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nexora.domain.analysis import Evidence, ReasonCode, Signal
from nexora.domain.ids import canonical_json, sha256_hex, stable_uuid
from nexora.domain.transfers import ObservedTransfer


class VerifiedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref: str = Field(min_length=1, max_length=120)
    kind: Literal["verified_business_activity", "confirmed_fraud_report"]
    subject: str = Field(min_length=1, max_length=128)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    observed_at: AwareDatetime
    known_at: AwareDatetime
    valid_until: AwareDatetime
    source_transaction_ids: frozenset[str]

    @model_validator(mode="after")
    def validate_window(self) -> VerifiedFact:
        if not self.observed_at <= self.known_at < self.valid_until or not self.source_transaction_ids:
            raise ValueError("invalid provenance interval or empty transaction set")
        return self


class VerifiedContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: AwareDatetime
    facts: tuple[VerifiedFact, ...]

    def manifest(self) -> str:
        facts = [
            fact.model_dump(mode="json", exclude={"source_transaction_ids"})
            | {"source_transaction_ids": sorted(fact.source_transaction_ids)}
            for fact in self.facts
            if fact.known_at <= self.as_of < fact.valid_until
        ]
        return sha256_hex(canonical_json([self.as_of.isoformat(), sorted(map(canonical_json, facts))]))


def observable(tx: ObservedTransfer, cutoff: datetime) -> bool:
    if tx.occurred_at is None:
        return tx.observed_date < cutoff.date()
    return tx.occurred_at <= cutoff


def corroboration(
    context: VerifiedContext, formation_id: str, subject: str, currency: str, transactions: list[ObservedTransfer]
) -> tuple[Evidence, Signal, ReasonCode] | None:
    source_ids = {tx.source_transaction_id for tx in transactions}
    if not source_ids or len(source_ids) != len(transactions):
        return None
    eligible = [
        fact
        for fact in context.facts
        if (fact.subject, fact.currency) == (subject, currency)
        and fact.known_at <= context.as_of < fact.valid_until
        and (
            source_ids <= fact.source_transaction_ids
            if fact.kind == "verified_business_activity"
            else bool(source_ids & fact.source_transaction_ids)
        )
    ]
    if not eligible:
        return None
    fact = min(eligible, key=lambda value: (value.kind, value.source_ref, value.known_at))
    positive = fact.kind == "confirmed_fraud_report"
    reason = "CONTEXT_CONFIRMED_REPORT" if positive else "CONTEXT_VERIFIED_BUSINESS_ACTIVITY"
    references = tuple(
        sorted(tx.transaction_id for tx in transactions if tx.source_transaction_id in fact.source_transaction_ids)
    )
    evidence_id = stable_uuid("evidence", formation_id, "network_context")
    observations = {
        "source_ref": fact.source_ref,
        "observed_at": fact.observed_at.isoformat(),
        "known_at": fact.known_at.isoformat(),
        "valid_until": fact.valid_until.isoformat(),
        "as_of": context.as_of.isoformat(),
    }
    return (
        Evidence(
            evidence_id,
            "counterevidence" if not positive else "aggregate_fact",
            reason,
            formation_id,
            references,
            (subject,),
            observations,
            {},
            (),
            "verified-context-v1",
        ),
        Signal(
            stable_uuid("signal", formation_id, "network_context"),
            formation_id,
            "NETWORK_CONTEXT",
            "network_context",
            "verified-context-v1",
            "supported" if positive else "contradicted",
            1.0 if positive else 0.0,
            (evidence_id,),
            (),
            ("verified_external_source",),
        ),
        ReasonCode(reason, {"source_ref": fact.source_ref, "covered_transfers": len(references)}),
    )
