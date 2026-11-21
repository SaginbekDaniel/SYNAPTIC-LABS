"""Benchmark harness: generator integrity, matching rule, metric arithmetic, determinism."""

from __future__ import annotations

import pytest

from nexora.analytics.config import default_config
from nexora.evaluation import benchmark as b
from nexora.evaluation.generator import ScenarioTruth, generate

CANONICAL_FIELDS = {
    "source_transaction_id",
    "sender_account_id",
    "receiver_account_id",
    "amount_minor",
    "currency",
    "observed_date",
    "occurred_at",
    "status",
}


@pytest.mark.parametrize(
    ("suite", "precision", "manifest_prefix"),
    [
        ("demo-v1", "day", "aa77e03856c86009"),
        ("demo-v1", "timestamp", "c2acc25ac6345dfe"),
        ("lookalikes-v1", "day", "ceac2d04c5778933"),
    ],
)
def test_demo_suites_are_unchanged_by_benchmark_extensions(suite, precision, manifest_prefix):
    """The UI demo and E2E tests rely on these datasets staying byte-identical."""
    assert generate(suite, 2026, precision=precision).manifest_sha256.startswith(manifest_prefix)


def test_bench_suite_is_deterministic_label_free_and_disjoint():
    a, again = generate("bench-v1", 1003), generate("bench-v1", 1003)
    assert a.manifest_sha256 == again.manifest_sha256 and a.truth_sha256 == again.truth_sha256
    assert all(set(r) == CANONICAL_FIELDS for r in a.rows)  # no label columns in detector input
    seen: set[str] = set()
    for t in a.truth:
        assert not (set(t.accounts) & seen), "scenarios must not share accounts"
        seen |= set(t.accounts)
    assert {t.label for t in a.truth} == {"suspicious", "legitimate"}


def test_splits_are_disjoint_and_hashes_are_stable():
    assert not set(b.SPLITS["dev"]) & set(b.SPLITS["validation"])
    assert not set(b.SPLITS["validation"]) & set(b.SPLITS["holdout"])
    ds = [generate("bench-v1", s) for s in b.SPLITS["dev"][:3]]
    assert b.split_hash(ds) == b.split_hash([generate("bench-v1", s) for s in b.SPLITS["dev"][:3]])


def _truth(sid, label, accounts):
    return ScenarioTruth(sid, f"F_{sid}", label, "easy", accounts, [], "")


def test_matching_requires_subject_and_overlap():
    truth = [_truth("s", "suspicious", ["A", "B", "C"]), _truth("n", "legitimate", ["X", "Y"])]
    item = b.ReviewItem(subject="C", accounts=frozenset({"A", "C", "Z"}), score=1.0)
    assert b.match(item, truth).scenario_id == "s"
    # subject outside every scenario: background, even with overlapping members
    assert b.match(b.ReviewItem(subject="Z", accounts=frozenset({"A", "B", "Z"}), score=1.0), truth) is None
    # a formation touching one scenario account only is not a match
    assert b.match(b.ReviewItem(subject="X", accounts=frozenset({"X", "Q"}), score=1.0), truth) is None
    # single-account baseline items match on the account itself
    assert b.match(b.ReviewItem(subject="Y", accounts=frozenset({"Y"}), score=1.0), truth).scenario_id == "n"


def test_summary_counts_scenarios_not_items():
    ds = generate("bench-v1", 1000)
    susp = [t for t in ds.truth if t.label == "suspicious"]
    legit = [t for t in ds.truth if t.label == "legitimate"]
    hit = susp[0]
    items = [
        # two alerts on the same suspicious scenario count once at scenario level
        b.ReviewItem(hit.accounts[0], frozenset(hit.accounts[:2]), 90.0, band="high", item_id="1"),
        b.ReviewItem(hit.accounts[1], frozenset(hit.accounts[:2]), 80.0, band="high", item_id="2"),
        b.ReviewItem(legit[0].accounts[0], frozenset(legit[0].accounts[:2]), 70.0, band="medium", item_id="3"),
        b.ReviewItem("background", frozenset({"background"}), 60.0, band="medium", item_id="4"),
    ]
    s = b.summarize([b.evaluate_items(ds, items, 0.01, 10)])
    sc = s["scenario"]
    assert (sc["tp"], sc["fp"], sc["fn"]) == (1, 1, len(susp) - 1)
    assert sc["precision"] == 0.5 and sc["recall"] == round(1 / len(susp), 4)
    assert sc["high_band_fpr"] == 0.0  # the legitimate hit is only medium
    assert (sc["tp_high"], sc["fp_high"]) == (1, 0)
    assert sc["high_band_recall"] == round(sc["tp_high"] / len(susp), 4)
    assert sc["f1"] == round(2 / (2 + 1 + len(susp) - 1), 4)
    assert s["alerts"] == {"flagged": 4, "per_dataset": 4.0, "relevant": 2, "precision": 0.5, "unmatched": 1}
    assert s["queue"]["p_at_5"] == 0.5


def test_f1_is_computed_from_counts_not_rounded_ratios():
    # tp=73, fp=48, fn=19: exact F1 = 146/213 = 0.685446…; from the rounded P (0.6033) and
    # R (0.7935) it would come out as 0.6855.
    ds = generate("bench-v1", 1000)
    ev = b.evaluate_items(ds, [], 0.0, 0)
    ev.truth = [ScenarioTruth(f"s{i}", "S1", "suspicious", "easy", [f"a{i}", f"b{i}"], [], "") for i in range(92)] + [
        ScenarioTruth(f"n{i}", "N1", "legitimate", "easy", [f"c{i}", f"d{i}"], [], "") for i in range(60)
    ]
    hits = [*ev.truth[:73], *ev.truth[92 : 92 + 48]]
    ev.items = [
        b.ReviewItem(t.accounts[0], frozenset(t.accounts), 1.0, band="medium", item_id=t.scenario_id) for t in hits
    ]
    ev.matches = [b.match(i, ev.truth) for i in ev.items]
    sc = b.summarize([ev])["scenario"]
    assert (sc["tp"], sc["fp"], sc["fn"]) == (73, 48, 19)
    assert sc["f1"] == 0.6854
    assert (sc["tp_high"], sc["fp_high"]) == (0, 0)


def test_unbanded_methods_have_no_high_band_counts():
    ds = generate("bench-v1", 1000)
    items = [b.ReviewItem(f"acc{i}", frozenset({f"acc{i}"}), float(i), item_id=f"acc{i}") for i in range(3)]
    sc = b.summarize([b.evaluate_items(ds, items, 0.0, 0)])["scenario"]
    assert sc["tp_high"] is None and sc["fp_high"] is None and sc["high_band_recall"] is None


def test_equal_budget_baseline_flags_top_n_only():
    ds = generate("bench-v1", 1000)
    items = [b.ReviewItem(f"acc{i}", frozenset({f"acc{i}"}), float(i), item_id=f"acc{i}") for i in range(10)]
    ev = b.evaluate_items(ds, items, 0.0, 0, budget=3)
    assert [i.subject for i in ev.items if i.flagged] == ["acc9", "acc8", "acc7"]


def test_harness_is_deterministic_and_v1_variant_disables_new_parts():
    cfg = default_config()
    v1 = b.config_variant(cfg, b.VARIANTS["v1_shipped"])
    assert v1.policy_version == "risk-policy-v1" and not v1.detectors["fan_out"]["enabled"]
    assert cfg.detectors["fan_out"]["enabled"] and cfg.policy_version == "risk-policy-v2"
    ds = [generate("bench-v1", s) for s in (1001, 1002)]
    exps = [b.Experiment("v2", b.nexora_method(cfg)), b.Experiment("v1", b.nexora_method(v1))]
    first, second = b.run_experiments(ds, exps), b.run_experiments(ds, exps)
    for name in ("v1", "v2"):
        assert b.identical_items(first[name], second[name])
        s1, s2 = b.summarize(first[name]), b.summarize(second[name])
        assert s1["scenario"] == s2["scenario"] and s1["queue"] == s2["queue"]
    assert not any(i.kind in ("fan_out", "cycle") for ev in first["v1"] for i in ev.items)


@pytest.mark.parametrize("pid", ["shuffled_rows", "duplicate_rows_5pct"])
def test_order_and_exact_duplicates_do_not_change_results(pid):
    ds = [generate("bench-v1", 2000)]
    exp = [b.Experiment("full", b.nexora_method(default_config()))]
    base = b.run_experiments(ds, exp)["full"]
    perturbed = b.run_experiments(ds, exp, transform=b.PERTURBATIONS[pid][0])["full"]
    assert b.identical_items(base, perturbed)


def test_background_perturbation_never_touches_planted_accounts():
    import random

    ds = generate("bench-v1", 2000)
    truth = {a for t in ds.truth for a in t.accounts}
    rows, _ = b.PERTURBATIONS["background_x4"][0](ds, random.Random(1))
    original = {r["source_transaction_id"] for r in ds.rows}
    added = [r for r in rows if r["source_transaction_id"] not in original]
    assert len(added) > 0
    assert not any(r["sender_account_id"] in truth or r["receiver_account_id"] in truth for r in added)
