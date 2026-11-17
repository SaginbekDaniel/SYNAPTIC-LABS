"""Competing-hypothesis engine: falsification logic, dependency groups, honesty under missing data."""

from __future__ import annotations

import random

from nexora.analytics.config import default_config
from nexora.analytics.evidence_validation import validate_evidence
from nexora.analytics.hypotheses.engine import REGISTRY, _score, _verdict
from nexora.analytics.pipeline import run_analysis
from nexora.domain.analysis import HypothesisTest
from tests.helpers import tx

CFG = default_config()
M = 1_000_000_00
CONTRACT = {"boundary_account_ids": [], "upstream_observed": True}


def _background(n: int = 30, seed: int = 7) -> list:
    rng = random.Random(seed)
    return [
        tx(f"b{a}-{k}", f"Q{a}", f"Q{(a + 3) % n}", M // 20, rng.randrange(0, 30)) for a in range(n) for k in range(6)
    ]


def _run(txs):
    return run_analysis(dataset_id="d", transfers=txs, contract=CONTRACT, config=CFG)


def _hub(out, kind):
    f = next(f for f in out.formations if f.kind == kind)
    h = next(h for h in out.hypotheses if h.formation_id == f.id)
    a = next(a for a in out.assessments if a.formation_id == f.id)
    return f, h, a


def _mule_collection():
    """Five one-off deposits within two days, forwarded the next day by a new account."""
    txs = [tx(f"in{i}", f"F{i}", "C", 3 * M, 10 + i % 2) for i in range(5)]
    return [*txs, tx("out", "C", "X", 14 * M, 12), *_background()]


def _recurring_business():
    txs = []
    for c in range(6):
        for k in range(5):
            txs.append(tx(f"c{c}-{k}", f"CUST{c}", "HUB", M // 2, 1 + 5 * k + c % 3))
    for k in range(10):
        txs.append(tx(f"pay{k}", "HUB", f"M{k % 3}", 3 * M // 2, 2 + 3 * k))
    return [*txs, *_background()]


def test_one_off_collection_favours_the_suspicious_explanation_but_keeps_untestable_alternatives():
    _f, h, a = _hub(_run(_mule_collection()), "funnel")
    assert h.verdict == "suspicious_explanation_favoured"
    untestable = {e.hypothesis_id for e in h.hypotheses if e.status == "untestable"}
    assert "one_off_legitimate_collection" in untestable  # never silently dropped
    assert "merchant_category" in h.unavailable_information
    assert "HYPOTHESIS_VERDICT" in {r.code for r in a.reason_codes}


def test_recurring_business_favours_the_benign_explanation_and_is_capped_not_deleted():
    out = _run(_recurring_business())
    f, h, a = _hub(out, "funnel")
    assert h.verdict == "benign_explanation_favoured"
    assert a.band == "low"
    assert f.features["hypothesis_verdict"] == "benign_explanation_favoured"
    # Stored with all its evidence: an analyst can still open it.
    assert {e.id for e in out.evidence} >= set(h.evidence_ids)


def test_recurrence_alone_cannot_clear_a_collection():
    """Adversarial: mules deposit on two different days (recurring) but the hub is new and bursty.
    One observation group for the benign explanation is not enough to favour it."""
    txs = [tx(f"in{i}-{k}", f"F{i}", "C", 2 * M, 10 + 3 * k + i % 2) for i in range(5) for k in range(2)]
    txs += [tx("out", "C", "X", 18 * M, 16), *_background()]
    _f, h, _a = _hub(_run(txs), "funnel")
    assert h.verdict != "benign_explanation_favoured"
    business = next(e for e in h.hypotheses if e.hypothesis_id == "recurring_business_activity")
    assert business.status != "supported"


def _t(test_id: str, group: str, result: str) -> HypothesisTest:
    return HypothesisTest(test_id=test_id, group=group, observation={}, expected="x", result=result, evidence_ids=())  # type: ignore[arg-type]


def test_dependent_observations_collapse_to_one_vote():
    """Turnover concentration and activity span read the same dates: one group, one vote."""
    spec = next(s for s in REGISTRY if s.hypothesis_id == "recurring_business_activity")
    tests = (
        _t("steady_turnover", "subject_activity", "consistent"),
        _t("established_activity", "subject_activity", "consistent"),
    )
    ev = _score(spec, tests)
    assert (ev.consistent_groups, ev.status) == (1, "not_established")
    mixed = (tests[0], _t("established_activity", "subject_activity", "inconsistent"))
    assert _score(spec, mixed).consistent_groups == 0 and _score(spec, mixed).inconsistent_groups == 0


def test_too_few_testable_groups_is_insufficient_data_not_a_verdict():
    susp = next(s for s in REGISTRY if s.hypothesis_id == "collection_through_intermediary")
    only_one = (_t("one_off_counterparties", "counterparty_relationship", "consistent"),)
    assert _verdict((_score(susp, only_one),)) == "insufficient_data"


def test_hypothesis_evidence_recomputes_and_ids_are_deterministic():
    a = _run(_mule_collection())
    b = _run(list(reversed(_mule_collection())))
    assert [h.id for h in a.hypotheses] == [h.id for h in b.hypotheses]
    assert [h.as_dict() for h in a.hypotheses] == [h.as_dict() for h in b.hypotheses]
    by_id = {e.id: e for e in a.evidence}
    for h in a.hypotheses:
        for e in h.hypotheses:
            for t in e.tests:
                for eid in t.evidence_ids:
                    validate_evidence(by_id[eid], a.snapshot.transfers)  # cited evidence exists and recomputes


def test_disabling_the_engine_restores_the_v2_assessment():
    from nexora.evaluation.benchmark import VARIANTS, config_variant

    v2 = config_variant(CFG, VARIANTS["v2_shipped"])
    out = run_analysis(dataset_id="d", transfers=_recurring_business(), contract=CONTRACT, config=v2)
    assert out.hypotheses == []
    assert all("HYPOTHESIS_VERDICT" not in {r.code for r in a.reason_codes} for a in out.assessments)


def test_no_hypothesis_or_reason_vocabulary_asserts_a_crime():
    banned = ("launder", "fraud", "criminal", "guilty", "proven")
    vocab = [s.hypothesis_id for s in REGISTRY] + [s.description for s in REGISTRY]
    assert not [v for v in vocab if any(w in v.lower() for w in banned)]
