"""The benchmark harness: determinism, split isolation, no label leakage, metric semantics."""

from __future__ import annotations

from functools import lru_cache

import pytest

from nexora.evaluation.benchmark import metrics
from nexora.evaluation.benchmark.methods import AccountBaseline, MethodResult, Prediction, volume_scorer
from nexora.evaluation.benchmark.scenarios import TruthRecord
from nexora.evaluation.benchmark.suite import FAMILIES, Suite, build_suite

CANONICAL_KEYS = {
    "source_transaction_id",
    "sender_account_id",
    "receiver_account_id",
    "amount_minor",
    "currency",
    "observed_date",
    "occurred_at",
    "status",
}


@lru_cache(maxsize=1)
def small_suite() -> Suite:
    return build_suite(master_seed=7, counts={"dev": 3, "val": 2, "test": 2})


def test_suite_is_deterministic() -> None:
    again = build_suite(master_seed=7, counts={"dev": 3, "val": 2, "test": 2})
    assert again.manifest() == small_suite().manifest()
    assert build_suite(master_seed=8, counts={"dev": 3, "val": 2, "test": 2}).manifest() != small_suite().manifest()


def test_splits_share_no_accounts_or_transactions() -> None:
    seen: dict[str, str] = {}
    for net in small_suite().networks:
        ids = {r["source_transaction_id"] for r in net.input.rows}
        ids |= {r["sender_account_id"] for r in net.input.rows} | {r["receiver_account_id"] for r in net.input.rows}
        for i in ids:
            assert seen.setdefault(i, net.split) == net.split, f"{i} appears in two splits"


def test_detector_input_carries_no_label() -> None:
    for net in small_suite().networks:
        assert all(set(r) == CANONICAL_KEYS for r in net.input.rows)
        assert set(net.input.coverage_contract) == {
            "source",
            "generator_version",
            "time_precision",
            "boundary_account_ids",
            "upstream_observed",
            "declared_complete",
        }
        assert all(r["amount_minor"].isdigit() for r in net.input.rows)


def test_every_family_present_and_scenario_transactions_exist() -> None:
    suite = small_suite()
    assert {n.truth.family for n in suite.networks} == {f.name for f in FAMILIES}
    for net in suite.networks:
        ids = {r["source_transaction_id"] for r in net.input.rows}
        assert net.truth.transaction_ids and set(net.truth.transaction_ids) <= ids


def test_boundary_declarations_are_not_label_specific() -> None:
    suite = build_suite(master_seed=2026, counts={"dev": 12}, splits=("dev",))
    with_boundary = [n for n in suite.networks if n.input.coverage_contract["boundary_account_ids"]]
    assert {n.truth.label for n in with_boundary} == {"suspicious", "benign"}


def _truth(accounts: tuple[str, ...], txs: tuple[str, ...], label: str = "suspicious") -> TruthRecord:
    return TruthRecord("n1", "F", "v", label, "easy", "detect", accounts, txs, "")  # type: ignore[arg-type]


def _pred(
    accounts: tuple[str, ...], txs: tuple[str, ...] = (), status: str = "raised", score: float = 1.0
) -> Prediction:
    return Prediction("p" + "".join(accounts), "chain", status, score, "high", accounts, txs)  # type: ignore[arg-type]


def test_matching_rule_requires_majority_overlap_and_shared_transaction() -> None:
    truth = _truth(("a", "b", "c"), ("t1", "t2"))
    assert metrics.matches(_pred(("a", "b", "x"), ("t1",)), truth)
    assert not metrics.matches(_pred(("a", "x", "y"), ("t1",)), truth)  # 1/3 accounts
    assert not metrics.matches(_pred(("a", "b"), ("t9",)), truth)  # no shared transaction
    assert metrics.matches(_pred(("b",)), truth)  # account-level prediction


def test_undefined_metrics_are_none_not_zero() -> None:
    assert metrics.ratio(0, 0) is None
    assert metrics.confusion([])["precision"] is None
    assert metrics.f1(None, 0.5) is None


def test_queue_counts_distinct_scenarios_only() -> None:
    truth = _truth(("a", "b"), ("t1",))
    benign = TruthRecord("n2", "N", "v", "benign", "easy", "no_alert", ("z",), ("t9",), "")
    ranked = [
        (900.0, "n1", _pred(("a", "b"), ("t1",)), truth),
        (800.0, "n1", _pred(("b", "a"), ("t1",)), truth),  # duplicate of the same scenario
        (700.0, "n2", _pred(("z",), ("t9",)), benign),
    ]
    q = metrics.queue_metrics(ranked, n_positive=1)
    assert q["10"]["hits"] == 1 and q["10"]["precision"] == 0.1 and q["10"]["recall"] == 1.0


def test_scenario_outcome_and_background_alerts() -> None:
    truth = _truth(("a", "b"), ("t1",))
    result = MethodResult(
        predictions=[_pred(("a", "b"), ("t1",)), _pred(("x", "y"), ("t7",)), _pred(("a",), ("t1",), "abstained")],
        latency_ms=1.0,
        n_transactions=3,
    )
    o = metrics.score_network("dev", truth, result, {"a", "b", "x", "y", "q"})
    assert (o.outcome, o.raised, o.raised_suspicious, o.raised_background) == ("TP", 2, 1, 1)
    assert (o.acc_tp, o.acc_fp, o.acc_fn, o.acc_tn) == (2, 2, 0, 1)


def test_best_threshold_prefers_strict_on_ties() -> None:
    f1, tau = metrics.best_f1_threshold([(True, 5.0), (False, 3.0), (True, 4.0)])
    assert (f1, tau) == (1.0, 4.0)


def test_baseline_refuses_to_run_unfitted() -> None:
    method = AccountBaseline("b", "volume", volume_scorer)
    with pytest.raises(RuntimeError):
        method.run(small_suite().networks[0].input)
