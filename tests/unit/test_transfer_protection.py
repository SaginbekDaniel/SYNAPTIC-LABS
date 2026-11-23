from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from nexora.analytics.config import default_config
from nexora.application.transfer_demo import PROFILE_PATH, SCENARIOS, load_policy, load_profiles
from nexora.application.transfer_protection import ContextFact, ContextKind, RecipientProfile, TimedTransfer, assess
from nexora.application.transfer_snapshot import prepare_profile
from scripts.prepare_transfer_demo import build_profiles, demo_row

POLICY = load_policy()
INTENT = SCENARIOS["mule"].intent(2_000_000)


def historical_transfers() -> tuple[TimedTransfer, ...]:
    cutoff = INTENT.as_of
    return tuple(
        demo_row(INTENT.recipient, f"history-{i}", INTENT.sender, INTENT.recipient, cutoff - timedelta(days=i), 500_000)
        for i in (8, 14, 21)
    )


def risky_transfers(known_later: bool = False) -> tuple[TimedTransfer, ...]:
    recipient = INTENT.recipient
    when = INTENT.as_of - timedelta(days=3)
    known_at = INTENT.as_of + timedelta(days=1) if known_later else None
    return (
        *(
            demo_row(recipient, f"pool-{i}", f"payer-{i}", recipient, when, 4_000_000, known_at=known_at)
            for i in range(5)
        ),
        demo_row(recipient, "payout", recipient, "onward", when + timedelta(days=1), 20_000_000, known_at=known_at),
    )


def prepare(
    transfers: tuple[TimedTransfer, ...],
    context: tuple[ContextFact, ...] = (),
) -> RecipientProfile:
    return prepare_profile(INTENT, transfers, context, default_config())


def test_committed_snapshots_rebuild_exactly() -> None:
    profiles = load_profiles(PROFILE_PATH)
    assert profiles
    assert {scenario: profile.model_dump(mode="json") for scenario, profile in profiles.items()} == build_profiles()


def test_late_and_future_transfers_have_no_effect_on_historical_assessment() -> None:
    history, late = historical_transfers(), risky_transfers(known_later=True)
    now = INTENT.as_of
    future = demo_row(
        INTENT.recipient, "future", "other", INTENT.recipient, now + timedelta(days=3), 25_000_000, known_at=now
    )
    late_report = ContextFact(
        source_ref="incident-register",
        kind="CONFIRMED_REPORT",
        recipient=INTENT.recipient,
        occurred_at=now - timedelta(days=1),
        known_at=now + timedelta(days=1),
    )
    earlier = prepare(history)
    with_out_of_scope = prepare((*late, future, *history), (late_report,))
    assert earlier == with_out_of_scope
    assert assess(INTENT, with_out_of_scope, POLICY) == assess(INTENT, earlier, POLICY)
    later = replace(INTENT, as_of=now + timedelta(days=2))
    later_snapshot = prepare_profile(later, (*history, future, *late), (late_report,), default_config())
    assert later_snapshot.snapshot_id != earlier.snapshot_id
    assert [item.source_ref for item in later_snapshot.context] == ["incident-register"]
    assert "future" not in {row.observed.source_transaction_id for row in later_snapshot.transactions}
    assert assess(later, later_snapshot, POLICY).decision == "STEP_UP"
    assert assess(INTENT, later_snapshot, POLICY).decision == "UNAVAILABLE"


def test_proposed_amount_never_becomes_graph_history_or_triggers_review() -> None:
    rows = historical_transfers()
    expensive_intent = replace(INTENT, amount_minor=10**38 - 1)
    profile = prepare(rows)
    assert prepare_profile(expensive_intent, rows, (), default_config()) == profile
    assert assess(expensive_intent, profile, POLICY).decision == "ALLOW"
    assert assess(expensive_intent, profile, POLICY).assessment_id != assess(INTENT, profile, POLICY).assessment_id


@pytest.mark.parametrize("kind", ["FAMILY_TRANSFER", "PAYROLL", "MERCHANT_SETTLEMENT", "REFUND"])
def test_legitimate_context_must_explain_the_observed_flow(kind: ContextKind) -> None:
    rows = risky_transfers()
    without_context = prepare(rows)
    assert assess(INTENT, without_context, POLICY).decision == "WARN"
    when = INTENT.as_of - timedelta(days=1)
    fact = ContextFact(
        source_ref="synthetic-document",
        kind=kind,
        recipient=INTENT.recipient,
        occurred_at=when,
        known_at=when,
        transaction_ids=tuple(row.observed.transaction_id for row in rows),
    )
    explained = prepare(rows, (fact,))
    assert assess(INTENT, explained, POLICY).reason_codes == ("EXPLAINED_ACTIVITY",)
    assert assess(INTENT, explained, POLICY).decision == "ALLOW"
    # Records accounting only for the incoming side should not excuse an unexplained payout.
    partial = fact.model_copy(update={"transaction_ids": fact.transaction_ids[:-1]})
    assert assess(INTENT, prepare(rows, (partial,)), POLICY).decision == "WARN"
    other_recipient = fact.model_copy(update={"recipient": "different-demo-recipient"})
    assert assess(INTENT, prepare(rows, (other_recipient,)), POLICY).decision == "WARN"


def test_correlated_formations_and_repeated_sender_do_not_overrule_the_policy() -> None:
    profile = prepare((*historical_transfers(), *risky_transfers()))
    assert profile.is_repeat_recipient
    overlap = profile.model_copy(update={"formations": profile.formations * 2})
    result = assess(INTENT, overlap, POLICY)
    assert result.decision == "WARN"
    assert result.reason_codes == ("SUSPICIOUS_NETWORK_LINK", "TEMPORAL_FLOW_CONFIRMED")


def test_missing_stale_partial_and_ambiguous_evidence_have_explicit_outcomes() -> None:
    rows = risky_transfers()
    partial = prepare_profile(INTENT, rows, (), default_config(), scope="partial")
    assert assess(INTENT, partial, POLICY).reason_codes == ("INCOMPLETE_GRAPH",)
    stale = prepare_profile(INTENT, rows, (), default_config(), valid_until=INTENT.as_of - timedelta(seconds=1))
    assert assess(INTENT, stale, POLICY).reason_codes == ("STALE_PROFILE",)
    day_only = tuple(
        TimedTransfer(observed=replace(row.observed, occurred_at=None, precision="day"), known_at=row.known_at)
        for row in rows
    )
    result = assess(INTENT, prepare(day_only), POLICY)
    assert result.decision == "LIMITED_SIGNAL"
    assert "AMBIGUOUS_TIMESTAMPS" in result.reason_codes
    assert assess(INTENT, None, POLICY).reason_codes == ("MISSING_PROFILE",)
    assert assess(INTENT, None, POLICY, failure="DEPENDENCY_FAILURE").decision == "UNAVAILABLE"


def test_a_new_recipient_and_an_unconfirmed_structure_do_not_trigger_an_intervention() -> None:
    profile = prepare(risky_transfers())
    no_temporal = tuple(
        f.model_copy(update={"indicators": tuple(i for i in f.indicators if i.family != "TEMPORAL")})
        for f in profile.formations
    )
    structure_only = profile.model_copy(update={"formations": no_temporal})
    assert not structure_only.is_repeat_recipient
    assert assess(INTENT, structure_only, POLICY).decision == "ALLOW"
