"""Evidence integrity checks (spec §13.4). Results with broken evidence are quarantined."""

from __future__ import annotations

from nexora.domain.analysis import Evidence
from nexora.domain.ids import canonical_json
from nexora.domain.transfers import ObservedTransfer

SUM_FIELDS = {"aggregate_fact": "total_minor", "graph_fact": "total_minor"}


class EvidenceIntegrityError(ValueError):
    pass


def validate_evidence(ev: Evidence, transfers: dict[str, ObservedTransfer]) -> None:
    missing = [t for t in ev.transaction_ids if t not in transfers]
    if missing:
        raise EvidenceIntegrityError(f"{ev.id}: unknown transaction ids {missing[:3]}")
    ineligible = [t for t in ev.transaction_ids if not transfers[t].eligible]
    if ineligible:
        raise EvidenceIntegrityError(f"{ev.id}: references non-posted transactions {ineligible[:3]}")
    try:
        canonical_json({"o": ev.observations, "t": ev.thresholds})  # rejects NaN/Infinity
    except ValueError as exc:
        raise EvidenceIntegrityError(f"{ev.id}: non-finite number in payload") from exc
    field = SUM_FIELDS.get(ev.kind)
    if field and field in ev.observations:
        claimed = int(ev.observations[field])
        actual = sum(transfers[t].amount_minor for t in ev.transaction_ids)
        if claimed != actual:
            raise EvidenceIntegrityError(f"{ev.id}: claimed {field}={claimed} but transactions sum to {actual}")
    if ev.kind == "temporal_fact":
        strict = int(ev.observations["strict_compatible_minor"])
        possible = int(ev.observations["possible_compatible_minor"])
        entry = int(ev.observations["entry_minor"])
        if not (0 <= strict <= possible <= entry):
            raise EvidenceIntegrityError(f"{ev.id}: compatible amounts violate 0<=strict<=possible<=entry")
