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
    assert s["alerts"] == {
        "flagged": 4,
        "per_dataset": 4.0,
        "precision": 0.5,
        "unmatched": 1,
        "per_flagged_network": 1.5,  # hit: 2 alerts, legitimate: 1
        "networks_with_duplicates": 0.5,
    }
    assert s["queue"]["p_at_5"] == 0.5


def test_equal_budget_baseline_flags_top_n_only():
    ds = generate("bench-v1", 1000)
    items = [b.ReviewItem(f"acc{i}", frozenset({f"acc{i}"}), float(i), item_id=f"acc{i}") for i in range(10)]
    ev = b.evaluate_items(ds, items, 0.0, 0, budget=3)
    assert [i.subject for i in ev.items if i.flagged] == ["acc9", "acc8", "acc7"]


def test_harness_is_deterministic_and_v1_variant_disables_new_parts():
    cfg = default_config()
    v1 = b.config_variant(cfg, b.VARIANTS["v1_shipped"])
    assert v1.policy_version == "risk-policy-v1" and not v1.detectors["fan_out"]["enabled"]
    assert cfg.detectors["fan_out"]["enabled"] and cfg.policy_version == "risk-policy-v3"
    assert "hypotheses" not in v1.detectors and "hypothesis" not in v1.risk_policy
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


# -- Audit additions: evaluation invariants (docs/architecture/LEAKAGE_ANALYSIS.md) ----------
def _ds(truth):
    from nexora.evaluation.generator import GeneratedDataset

    return GeneratedDataset("t", 1, "day", [], {}, truth, (None, None))  # type: ignore[arg-type]


def _item(subject, accounts, score, band="high"):
    return b.ReviewItem(
        subject=subject, accounts=frozenset(accounts), score=score, band=band, band_rank=b.BAND_RANK[band],
        flagged=band in b.FLAG_BANDS, item_id=f"{subject}{score}",
    )  # fmt: skip


def test_duplicate_alerts_on_one_network_do_not_inflate_distinct_precision_or_recall():
    truth = [_truth("s1", "suspicious", ["A", "B", "C"]), _truth("s2", "suspicious", ["P", "Q"])]
    dupes = [_item("A", {"A", "B"}, 90 - i) for i in range(5)]  # five alerts, same planted network
    ev = b.evaluate_items(_ds(truth), dupes, 0.0, 0)
    summary = b.summarize([ev])
    assert summary["scenario"]["tp"] == 1 and summary["scenario"]["recall"] == 0.5
    assert summary["queue"]["p_at_5"] == 1.0  # raw alert precision counts every duplicate
    assert summary["queue"]["distinct_p_at_5"] == 0.2  # one new network in five alerts
    assert summary["alerts"]["per_flagged_network"] == 5.0
    assert summary["alerts"]["networks_with_duplicates"] == 1.0


def test_unlabelled_alerts_count_against_alert_precision():
    truth = [_truth("s1", "suspicious", ["A", "B"])]
    items = [_item("A", {"A", "B"}, 9), _item("Z", {"Z", "W"}, 8)]  # second alert matches nothing planted
    summary = b.summarize([b.evaluate_items(_ds(truth), items, 0.0, 0)])
    assert summary["alerts"]["flagged"] == 2 and summary["alerts"]["unmatched"] == 1
    assert summary["alerts"]["precision"] == 0.5


def test_single_shared_account_does_not_match_a_multi_account_item():
    """Partial overlap of one account (the subject) is not enough when the item lists several accounts."""
    truth = [_truth("s1", "suspicious", ["A", "B", "C"])]
    item = _item("A", {"A", "X", "Y"}, 9)
    assert b.match(item, truth) is None


def test_abstention_share_exposes_a_label_leaking_boundary():
    truth = [_truth("s1", "suspicious", ["A", "B"]), _truth("n1", "legitimate", ["N", "M"])]
    items = [_item("A", {"A", "B"}, -1, band="insufficient_evidence")]
    summary = b.summarize([b.evaluate_items(_ds(truth), items, 0.0, 0)])
    assert summary["abstention"] == {"rate": 1.0, "suspicious_share": 1.0}


def test_sealed_split_is_disjoint_from_every_exposed_split_and_label_blind():
    from nexora.evaluation.sealed_generator import generate_sealed

    for name in b.EXPOSED_SPLITS:
        assert not set(b.SPLITS["sealed"]) & set(b.SPLITS[name])
    ds = generate_sealed(b.SPLITS["sealed"][0])
    assert all(set(r) == CANONICAL_FIELDS for r in ds.rows)
    planted_legit = {a for t in ds.truth if t.label == "legitimate" for a in t.accounts}
    boundary = set(ds.coverage_contract["boundary_account_ids"])
    everyone = {r["sender_account_id"] for r in ds.rows} | {r["receiver_account_id"] for r in ds.rows}
    assert boundary <= everyone
    # Boundary accounts are sampled from all accounts, not only from planted fraud centres.
    assert boundary - {a for t in ds.truth if t.label == "suspicious" for a in t.accounts}
    assert planted_legit  # the dataset contains legitimate lookalikes


def test_v2_shipped_variant_reconstructs_the_merged_configuration_exactly():
    """The sealed baseline must be the configuration merged at 4c01a7a, byte for byte."""
    import yaml

    v2 = b.config_variant(default_config(), b.VARIANTS["v2_shipped"])
    assert v2.config_sha256 == "489b477a3da5ac1b" + v2.config_sha256[16:]
    assert v2.detectors["funnel"]["returning_min_ratio"] == 0.1
    assert yaml.safe_dump(v2.risk_policy) and "hypothesis" not in v2.risk_policy


def test_committed_benchmark_artifact_validates_against_the_api_schema():
    """GET /api/v1/evaluation serves this file; a harness change must not make it a 500."""
    import json
    from pathlib import Path

    from nexora.api.schemas import EvaluationReport
    from nexora.application.evaluation import load_report

    root = Path(__file__).resolve().parents[2]
    assert json.loads((root / "benchmarks/results/bench-v1.json").read_text())["schema_version"] == 1
    EvaluationReport.model_validate(load_report("benchmarks/results/bench-v1.json"))
