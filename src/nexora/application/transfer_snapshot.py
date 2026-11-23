"""Offline preparation using the existing evidence-validating graph pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from nexora.analytics.config import AnalysisConfig
from nexora.analytics.pipeline import run_analysis
from nexora.application.transfer_protection import (
    ContextFact,
    FormationProfile,
    Indicator,
    Limitation,
    RecipientProfile,
    Scope,
    TimedTransfer,
    TransferIntent,
)


def prepare_profile(
    intent: TransferIntent,
    history: tuple[TimedTransfer, ...],
    context: tuple[ContextFact, ...],
    config: AnalysisConfig,
    *,
    scope: Scope = "complete",
    valid_until: datetime | None = None,
) -> RecipientProfile:
    available = sorted(
        (row for row in history if row.available(intent.as_of) and row.observed.currency == intent.currency),
        key=lambda row: row.observed.transaction_id,
    )
    transactions = {row.observed.transaction_id: row for row in available if row.observed.eligible}
    graph = run_analysis(
        dataset_id=f"transfer-profile:{intent.recipient}",
        transfers=[row.observed for row in available],
        contract={
            "upstream_observed": scope == "complete",
            "boundary_account_ids": [intent.recipient] if scope == "partial" else [],
        },
        config=config,
    )
    evidence = {e.id: e for e in graph.evidence}
    risk = {a.formation_id: a for a in graph.assessments}
    formations = tuple(
        FormationProfile(
            formation_id=f.id,
            kind=f.kind,
            band=risk[f.id].band,
            limitations=f.limitations,
            indicators=tuple(
                Indicator(
                    evidence_id=ev.id,
                    family=s.family,
                    status=s.status,
                    reason_code=ev.reason_code,
                    transaction_ids=ev.transaction_ids,
                )
                for s in graph.signals
                if s.formation_id == f.id
                for evidence_id in s.evidence_ids
                for ev in (evidence[evidence_id],)
            ),
        )
        for f in graph.formations
        if f.subject_account_id == intent.recipient
    )
    observed = [
        row for row in transactions.values() if intent.recipient in (row.observed.sender, row.observed.receiver)
    ]
    context_available = tuple(
        sorted(
            (
                item
                for item in context
                if item.recipient == intent.recipient
                and max(item.occurred_at, item.known_at) <= intent.as_of
                and set(item.transaction_ids) <= transactions.keys()
            ),
            key=lambda item: item.source_ref,
        )
    )
    limitations: list[Limitation] = []
    # Minimum demo history is two distinct observed days, including days of formation evidence.
    evidence_ids = {tx for f in formations for i in f.indicators for tx in i.transaction_ids}
    relevant = {row.observed.transaction_id for row in observed} | evidence_ids
    if len({transactions[tx].observed.observed_date for tx in relevant}) < 2:
        limitations.append("INSUFFICIENT_HISTORY")
    if (
        scope == "partial"
        or graph.partial_reasons
        or graph.quarantined
        or any(
            {"boundary_limited", "downstream_unobserved", "upstream_unknown"} & set(f.limitations) for f in formations
        )
    ):
        limitations.append("INCOMPLETE_GRAPH")
    if any(i.family == "TEMPORAL" and i.status == "possible_ambiguous" for f in formations for i in f.indicators) or (
        observed and all(row.observed.precision == "day" for row in observed)
    ):
        limitations.append("AMBIGUOUS_TIMESTAMPS")

    in_scope = relevant | {tx for fact in context_available for tx in fact.transaction_ids}
    fields: dict[str, Any] = {
        "snapshot_id": "",
        "recipient": intent.recipient,
        "sender": intent.sender,
        "currency": intent.currency,
        "as_of": intent.as_of,
        "valid_until": valid_until if valid_until is not None else intent.as_of + timedelta(days=2),
        "graph_snapshot_id": graph.snapshot_id,
        "graph_config_sha256": graph.config_sha256,
        "graph_policy_version": graph.policy_version,
        "limitations": tuple(limitations),
        "is_repeat_recipient": len(
            {
                row.observed.observed_date
                for row in observed
                if row.observed.sender == intent.sender and row.observed.receiver == intent.recipient
            }
        )
        >= 2,
        "formations": formations,
        "transactions": tuple(transactions[tx] for tx in sorted(in_scope)),
        "context": context_available,
    }
    fields["snapshot_id"] = RecipientProfile.model_construct(**fields).identity()
    return RecipientProfile.model_validate(fields)
