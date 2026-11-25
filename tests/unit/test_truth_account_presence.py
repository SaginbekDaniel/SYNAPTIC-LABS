"""Finding H-25: ground-truth accounts that never occur in the generated rows.

A truth list should name exactly the accounts of a scenario's transactions. Some builders of the frozen
generators list accounts they never use, so those accounts can never be flagged: account-level recall
counts them as positives that no method can reach. The frozen generators and their artifacts are not
changed (bench-v1 is pinned, sealed-v1 is consumed); this test pins the defect's exact size so it cannot
grow or spread unnoticed, and requires ``sealed-gen-v2`` to stay free of it. Data only: no detector runs.
"""

from __future__ import annotations

from functools import cache

import pytest

from nexora.evaluation import benchmark as b

# split -> (suspicious truth accounts absent / total, legitimate-only absent / total, boundary absent / declared),
# all summed over the split's datasets. Recorded 2026-11-23 (MASTER_HANDOFF H-25).
KNOWN = {
    "dev": ((0, 764), (25, 1809), (0, 5)),
    "validation": ((0, 414), (10, 1202), (0, 5)),
    "holdout": ((1, 735), (17, 1810), (0, 8)),
    "sealed": ((4, 1740), (45, 5099), (9, 872)),
    "sealed_v2": ((0, 2540), (0, 6572), (0, 1165)),
}


@cache
def _absent(split: str) -> tuple[tuple[int, int], ...]:
    counts = [0] * 6
    for ds in b.load_split(split):
        present = {r["sender_account_id"] for r in ds.rows} | {r["receiver_account_id"] for r in ds.rows}
        positive: set[str] = set()
        legitimate: set[str] = set()
        for t in ds.truth:
            (positive if t.label == "suspicious" else legitimate).update(t.accounts)
        legitimate -= positive  # the convention of entity_metrics.account_counts
        boundary = set(ds.coverage_contract.get("boundary_account_ids") or [])
        for i, group in enumerate((positive, legitimate, boundary)):
            counts[2 * i] += len(group - present)
            counts[2 * i + 1] += len(group)
    return tuple((counts[i], counts[i + 1]) for i in range(0, 6, 2))


@pytest.mark.parametrize("split", sorted(KNOWN))
def test_absent_truth_accounts_match_the_recorded_finding(split: str):
    assert _absent(split) == KNOWN[split]


def test_every_scenario_keeps_at_least_two_transacting_accounts():
    """Why scenario-level results are unaffected: matching needs two accounts of a review item in the
    scenario (``benchmark.match``), absent accounts never appear in an item, and every scenario still has
    two accounts that do."""
    for split in KNOWN:
        for ds in b.load_split(split):
            present = {r["sender_account_id"] for r in ds.rows} | {r["receiver_account_id"] for r in ds.rows}
            for t in ds.truth:
                assert len(set(t.accounts) & present) >= 2, (split, ds.seed, t.scenario_id)
                assert t.accounts[0] in present, (split, ds.seed, t.scenario_id)
