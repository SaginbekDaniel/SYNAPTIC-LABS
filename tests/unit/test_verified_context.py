from datetime import UTC, datetime, timedelta

from nexora.analytics.config import AnalysisConfig, default_config, experimental_config
from nexora.analytics.context import VerifiedContext, VerifiedFact
from nexora.analytics.pipeline import run_analysis
from tests.helpers import tx

CUTOFF = datetime(2026, 7, 15, tzinfo=UTC)


def ledger():
    return [tx("ab", "a", "b", 8_000_000, 1), tx("bc", "b", "c", 8_000_000, 2), tx("cd", "c", "d", 8_000_000, 3)]


def fact(*, report=False, late=False, currency="KZT", ids=frozenset({"ab", "bc", "cd"})):
    return VerifiedFact(
        source_ref="trusted-synthetic-receipt",
        kind="confirmed_fraud_report" if report else "verified_business_activity",
        subject="d",
        currency=currency,
        observed_at=CUTOFF - timedelta(days=3),
        known_at=CUTOFF + timedelta(days=1 if late else -1),
        valid_until=CUTOFF + timedelta(days=2),
        source_transaction_ids=ids,
    )


def analyze(facts=(), *, stable=False, transfers=None):
    return run_analysis(
        dataset_id="same-ledger",
        transfers=transfers if transfers is not None else ledger(),
        contract={"declared_complete": True},
        config=default_config() if stable else experimental_config(),
        context=VerifiedContext(as_of=CUTOFF, facts=facts),
    )


def test_verified_context_preserves_evidence_and_caps_only_matched_formations():
    before, after = analyze(), analyze((fact(),))
    assert before.assessments[0].band in {"medium", "high"}
    assert after.assessments[0].band == "low"
    assert before.assessments[0].priority == after.assessments[0].priority
    assert before.snapshot_id != after.snapshot_id
    item = next(evidence for evidence in after.evidence if evidence.reason_code == "CONTEXT_VERIFIED_BUSINESS_ACTIVITY")
    assert set(item.transaction_ids) == {"ab", "bc", "cd"}
    assert item.observations["source_ref"] == "trusted-synthetic-receipt"
    assert (
        next(r for r in before.assessments[0].reason_codes if r.code == "PRIORITY_CONTRIBUTIONS").params[
            "policy_ceiling"
        ]
        == 100
    )


def test_unavailable_partial_or_wrong_currency_context_does_not_exempt():
    before = analyze()
    for candidate in (fact(late=True), fact(currency="USD"), fact(ids=frozenset({"ab", "bc"}))):
        observed = analyze((candidate,))
        assert observed.assessments[0].band == before.assessments[0].band
        assert "NETWORK_CONTEXT" in observed.assessments[0].missing_families
    assert analyze((fact(late=True),)).snapshot_id == before.snapshot_id


def test_independent_report_takes_priority_over_business_receipt():
    after = analyze((fact(), fact(report=True, ids=frozenset({"ab"}))))
    assert "NETWORK_CONTEXT" in after.assessments[0].supported_families
    assert after.assessments[0].band in {"high", "critical"}
    assert "CONTEXT_CONFIRMED_REPORT" in {reason.code for reason in after.assessments[0].reason_codes}


def test_point_in_time_filter_omits_future_transfer_and_keeps_stable_policy_unchanged():
    rows = [*ledger(), tx("future", "x", "y", 1, 30)]
    assert "future" not in analyze(transfers=rows).snapshot.transfers
    assert (
        analyze((fact(),), stable=True, transfers=rows).snapshot_id == analyze(stable=True, transfers=rows).snapshot_id
    )


def test_currency_specific_thresholds_only_affect_the_configured_currency():
    stable = default_config()
    adjusted = AnalysisConfig(
        detectors={**stable.detectors, "currency_thresholds": {"USD": {"chain": {"min_edge_minor": "1"}}}},
        risk_policy=stable.risk_policy,
    )
    transfers = [
        tx(f"{currency}-{index}", f"{currency}{index}", f"{currency}{index + 1}", 800, index, currency=currency)
        for currency in ("KZT", "USD")
        for index in range(3)
    ]
    result = run_analysis(dataset_id="currency", transfers=transfers, contract={}, config=adjusted)
    assert {(row.kind, row.currency) for row in result.formations} == {("chain", "USD")}
