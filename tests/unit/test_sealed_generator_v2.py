"""Generator properties of ``sealed-gen-v2`` (backlog B-040).

These tests look at the generated data and its ground truth only. No detector, policy or analysis runs on
``sealed-v2`` data here: the split must stay unseen until its protocol is locked and the single run happens.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from functools import cache

import pytest

from nexora.evaluation import benchmark as b
from nexora.evaluation.generator import GeneratedDataset
from nexora.evaluation.sealed_generator_v2 import (
    LEGITIMATE,
    SEALED_V2_GENERATOR_VERSION,
    SUSPICIOUS,
    WINDOW_DAYS,
    generate_sealed_v2,
)

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
SEEDS = b.SPLITS["sealed_v2"]


@cache
def _split() -> tuple[GeneratedDataset, ...]:
    return tuple(generate_sealed_v2(s) for s in SEEDS)


def test_seeds_are_disjoint_from_every_other_split():
    assert len(SEEDS) == 80
    for name, seeds in b.SPLITS.items():
        if name != "sealed_v2":
            assert not set(SEEDS) & set(seeds), name


def test_generation_is_deterministic_per_seed():
    a, c = generate_sealed_v2(SEEDS[3]), generate_sealed_v2(SEEDS[3])
    assert a.rows == c.rows and a.truth == c.truth and a.coverage_contract == c.coverage_contract
    assert b.split_hash(list(_split()[:5])) == b.split_hash([generate_sealed_v2(s) for s in SEEDS[:5]])
    assert generate_sealed_v2(SEEDS[4]).rows != a.rows


def test_rows_are_canonical_valid_and_inside_the_window():
    for ds in _split():
        start, end = ds.window
        assert (end - start).days == WINDOW_DAYS - 1
        ids = [r["source_transaction_id"] for r in ds.rows]
        assert len(ids) == len(set(ids))
        for r in ds.rows:
            assert set(r) == CANONICAL_FIELDS
            assert int(r["amount_minor"]) >= 1 and r["currency"] == "KZT" and r["status"] == "posted"
            assert r["sender_account_id"] != r["receiver_account_id"]
            assert start <= date.fromisoformat(r["observed_date"]) <= end
            if ds.precision == "timestamp":
                assert r["occurred_at"].startswith(r["observed_date"]) and r["occurred_at"].endswith("Z")
            else:
                assert r["occurred_at"] == ""


def test_ground_truth_never_enters_rows_or_the_contract():
    for ds in _split()[:10]:
        text = repr(ds.rows) + repr(ds.coverage_contract)
        for t in ds.truth:
            assert t.scenario_id not in text and t.family not in text and t.notes not in text
        assert "suspicious" not in text and "legitimate" not in text
        assert set(ds.coverage_contract) == {
            "source",
            "generator_version",
            "time_precision",
            "boundary_account_ids",
            "upstream_observed",
            "declared_complete",
        }
        assert ds.coverage_contract["generator_version"] == SEALED_V2_GENERATOR_VERSION


def test_truth_lists_are_complete_and_scenarios_never_share_accounts():
    for ds in _split():
        by_tx = {r["source_transaction_id"]: r for r in ds.rows}
        owner: dict[str, str] = {}
        for t in ds.truth:
            members = set(t.accounts)
            assert len(members) == len(t.accounts) >= 2
            assert t.source_transaction_ids, t.scenario_id
            for tid in t.source_transaction_ids:
                r = by_tx[tid]  # every scenario transaction is in the data
                # Complete lists: both ends of every scenario transaction are scenario accounts.
                assert {r["sender_account_id"], r["receiver_account_id"]} <= members, t.scenario_id
            for a in members:
                assert owner.setdefault(a, t.scenario_id) == t.scenario_id, f"{a} shared"
        touched = {a for r in ds.rows for a in (r["sender_account_id"], r["receiver_account_id"])}
        assert set(owner) <= touched


def test_boundary_declarations_are_label_blind():
    """A declared boundary account must not tell suspicious from legitimate (audit L-01)."""
    centres = Counter()
    sampled_in_scenarios = Counter()
    for ds in _split():
        boundary = set(ds.coverage_contract["boundary_account_ids"])
        accounts = {a for r in ds.rows for a in (r["sender_account_id"], r["receiver_account_id"])}
        assert boundary <= accounts
        for t in ds.truth:
            if t.family in ("SV4_boundary_collection", "LV10_boundary_merchant"):
                assert t.accounts[0] in boundary  # the centre of a boundary scenario is declared
                centres[t.label] += 1
            sampled_in_scenarios[t.label] += len(boundary & set(t.accounts[1:]))
        unlabelled = accounts - {a for t in ds.truth for a in t.accounts}
        assert boundary & unlabelled or not unlabelled  # background accounts are sampled too
    # Boundary centres occur for both labels, and the random sample reaches both labels' non-centre accounts.
    assert centres["suspicious"] > 0 and centres["legitimate"] > 0
    assert sampled_in_scenarios["suspicious"] > 0 and sampled_in_scenarios["legitimate"] > 0


def test_every_family_occurs_and_every_dataset_has_both_labels():
    families = Counter(t.family for ds in _split() for t in ds.truth)
    assert set(families) == {name for name, _, _ in SUSPICIOUS} | {name for name, _, _ in LEGITIMATE}
    for ds in _split():
        labels = {t.label for t in ds.truth}
        assert labels == {"suspicious", "legitimate"}
    assert {ds.precision for ds in _split()} == {"day", "timestamp"}


@pytest.mark.parametrize("family", ["SV2_two_tier_collection", "SV3_scatter_gather", "LV11_property_escrow"])
def test_new_families_have_their_documented_shape(family):
    ds = next(d for d in _split() if any(t.family == family for t in d.truth))
    t = next(t for t in ds.truth if t.family == family)
    rows = [r for r in ds.rows if r["source_transaction_id"] in set(t.source_transaction_ids)]
    senders = Counter(r["sender_account_id"] for r in rows)
    receivers = Counter(r["receiver_account_id"] for r in rows)
    if family == "SV2_two_tier_collection":
        # The hub (first account) receives from every sub-collector and pays one exit.
        assert receivers[t.accounts[0]] >= 2 and senders[t.accounts[0]] == 1
    elif family == "SV3_scatter_gather":
        # One source pays every intermediary; every intermediary pays the same destination.
        assert senders[t.accounts[0]] == len(t.accounts) - 2 == receivers[t.accounts[-1]]
    else:
        # One buyer payment into escrow, then 3-6 releases summing exactly to the price.
        inbound = [r for r in rows if r["receiver_account_id"] == t.accounts[1]]
        outbound = [r for r in rows if r["sender_account_id"] == t.accounts[1]]
        assert len(inbound) == 1 and 3 <= len(outbound) <= 6
        assert sum(int(r["amount_minor"]) for r in outbound) == int(inbound[0]["amount_minor"])
