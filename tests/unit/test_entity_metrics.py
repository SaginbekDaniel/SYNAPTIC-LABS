"""Entity-level, ranking and reliability metrics pinned by a hand-computed fixture (backlog B-041)."""

from __future__ import annotations

import pytest

from nexora.evaluation import entity_metrics as em
from nexora.evaluation.benchmark import BAND_RANK, DatasetEval, ReviewItem, match
from nexora.evaluation.generator import ScenarioTruth


def _truth(sid: str, label: str, accounts: list[str]) -> ScenarioTruth:
    return ScenarioTruth(sid, sid, label, "standard", accounts, [], "")  # type: ignore[arg-type]


def _item(subject: str, accounts: set[str], band: str | None, score: float, *, flagged=True, queued=True, iid=""):
    return ReviewItem(
        subject=subject,
        accounts=frozenset(accounts),
        score=score,
        band_rank=BAND_RANK[band] if band else 0,
        flagged=flagged,
        queued=queued,
        band=band,
        priority=int(score) if band else None,
        item_id=iid or subject + "".join(sorted(accounts)),
    )


def _dataset(items: list[ReviewItem], truth: list[ScenarioTruth], dsid: str = "A") -> DatasetEval:
    return DatasetEval(dsid, 1, "day", truth, items, [match(i, truth) for i in items], 0.0, 0)


TRUTH = [
    _truth("S1", "suspicious", ["a", "b", "c"]),
    _truth("S2", "suspicious", ["d", "e"]),
    _truth("L1", "legitimate", ["x", "y"]),
]
ITEMS = [
    _item("a", {"b"}, "high", 70),  # finds S1
    _item("a", {"c"}, "high", 70),  # same key (tie), duplicate alert on S1
    _item("x", {"y"}, "medium", 40),  # legitimate network flagged
    _item("d", {"e"}, "insufficient_evidence", -1, flagged=False),  # abstention: queued, not flagged; finds S2
    _item("q", {"r"}, "low", 10, flagged=False, queued=False),  # background, never alerted
]


def test_account_level_counts_by_hand():
    acc = em.accounts([_dataset(ITEMS, TRUTH)])
    # positives a b c d e; flagged = accounts and subjects of flagged items = a b c x y
    assert acc == {
        "positive": 5,
        "flagged": 5,
        "tp": 3,
        "fp": 2,
        "fn": 2,
        "fp_labelled_legitimate": 2,
        "fp_unlabelled": 0,
        "recall": 0.6,
        "precision": 0.6,
    }


def test_counts_sum_over_datasets_and_unlabelled_accounts_are_separated():
    other = _dataset([_item("m", {"n"}, None, 3.0)], [_truth("S9", "suspicious", ["z"])], "B")
    acc = em.accounts([_dataset(ITEMS, TRUTH), other])
    assert (acc["positive"], acc["flagged"], acc["tp"], acc["fp_unlabelled"]) == (6, 7, 3, 2)
    assert acc["precision"] == round(3 / 7, 4) and acc["recall"] == 0.5


def test_ranking_groups_ties_and_counts_distinct_networks():
    r = em.ranking([_dataset(ITEMS, TRUTH)])
    # Step 1: the tied pair (2 items) reaches S1 → recall 1/2 at precision 1/2.
    # Step 2: the medium item adds nothing. Step 3: the abstention reaches S2 → recall 2/2 at precision 2/4.
    assert r["curve"] == [{"items": 2, "networks": 1}, {"items": 4, "networks": 2}]
    assert r["average_precision"] == 0.5  # 1/2·1/2 + 1/2·2/4
    assert (r["suspicious_networks"], r["queued_items"], r["networks_reached"]) == (2, 4, 2)
    assert em.average_precision_from_curve(r["curve"], r["suspicious_networks"]) == r["average_precision"]


def test_ranking_does_not_depend_on_tie_order_or_input_order():
    shuffled = [ITEMS[1], ITEMS[0], *ITEMS[2:]]
    assert em.ranking([_dataset(shuffled, TRUTH)]) == em.ranking([_dataset(ITEMS, TRUTH)])


def test_ranking_without_planted_networks_has_no_ap():
    r = em.ranking([_dataset([_item("x", {"y"}, "high", 50)], [_truth("L1", "legitimate", ["x", "y"])])])
    assert r["average_precision"] is None and r["curve"] == []


def test_reliability_by_band_with_wilson_intervals():
    rows = em.reliability([_dataset(ITEMS, TRUTH)])
    assert [(r["band"], r["items"], r["planted"]) for r in rows] == [
        ("high", 2, 2),
        ("medium", 1, 0),
        ("insufficient_evidence", 1, 1),
        ("low", 1, 0),
    ]
    assert rows[0]["share"] == 1.0 and rows[0]["wilson95"] == [0.3424, 1.0]
    assert em.reliability([_dataset([_item("m", {"n"}, None, 1.0)], TRUTH)]) is None  # unbanded method


@pytest.mark.parametrize(
    ("k", "n", "expected"),
    [(5, 10, (0.2366, 0.7634)), (0, 10, (0.0, 0.2775)), (10, 10, (0.7225, 1.0)), (1, 1, (0.2065, 1.0))],
)
def test_wilson_reference_values(k, n, expected):
    assert em.wilson(k, n) == expected


def test_wilson_undefined_without_trials():
    assert em.wilson(0, 0) is None


def test_bootstrap_is_deterministic_and_collapses_for_identical_datasets():
    same = [_dataset(ITEMS, TRUTH, "A"), _dataset(ITEMS, TRUTH, "B")]
    b1 = em.bootstrap(same, draws=200)
    assert b1 == em.bootstrap(same, draws=200)
    assert b1["account_recall"] == [0.6, 0.6] and b1["average_precision"] == [0.5, 0.5]
    mixed = [_dataset(ITEMS, TRUTH, "A"), _dataset([_item("x", {"y"}, "high", 99)], TRUTH, "B")]
    lo, hi = em.bootstrap(mixed, draws=500)["account_recall"]
    assert 0.0 <= lo < hi <= 0.6
