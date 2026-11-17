import dataclasses
import random

import pytest

from nexora.analytics.config import AnalysisConfig, default_config
from nexora.analytics.evidence_validation import EvidenceIntegrityError, validate_evidence
from nexora.analytics.pipeline import run_analysis
from nexora.analytics.risk import assess, opens_alert
from nexora.domain.analysis import CoverageAssessment, Evidence, Signal
from nexora.domain.ids import transaction_uuid
from nexora.domain.transfers import ObservedTransfer
from nexora.evaluation.generator import SUITES, generate
from nexora.ingest.validation import prepare_batch
from tests.helpers import tx

CFG = default_config()
POLICY = CFG.risk_policy
NO_COVERAGE = CoverageAssessment(limitations=(), subject_limitations=(), boundary_accounts=(), data_requests=())


def sig(family, status="supported", strength=1.0, sid=None):
    return Signal(
        sid or f"{family}-{status}-{strength}", "F", family, f"d.{family}", "v1", status, strength, (), (), ()
    )


def _assess(signals, coverage=NO_COVERAGE):
    return assess(formation_id="F", signals=signals, coverage=coverage, reasons=[], policy=POLICY, policy_sha256="x")


def test_correlated_structural_signals_get_single_credit():  # RISK-001
    one = _assess([sig("STRUCTURE"), sig("TEMPORAL")])
    two = _assess([sig("STRUCTURE", sid="a"), sig("STRUCTURE", sid="b"), sig("TEMPORAL")])
    assert one.priority == two.priority == 65


def test_missing_temporal_family_caps_band_without_renormalising():  # RISK-002
    a = _assess([sig("STRUCTURE"), sig("TEMPORAL", "unavailable", None)])
    assert a.priority == 35 and a.band == "medium"
    assert "TEMPORAL" in a.missing_families


def test_no_corroboration_never_high():  # RISK-004
    a = _assess([sig("STRUCTURE")])
    assert a.band in {"low", "medium"}
    assert any(r.code == "NO_INDEPENDENT_CORROBORATION" for r in a.reason_codes)


def test_contradicted_chronology_caps_to_low():
    a = _assess([sig("STRUCTURE"), sig("TEMPORAL", "contradicted", 0.0)])
    assert a.band == "low" and not opens_alert(a.band, POLICY)


def test_subject_at_boundary_abstains():  # COVER-001
    cov = CoverageAssessment(("boundary_limited",), ("boundary_limited",), ("C",), ())
    a = _assess([sig("STRUCTURE"), sig("TEMPORAL")], cov)
    assert a.band == "insufficient_evidence" and a.priority is None
    assert opens_alert(a.band, POLICY)  # unresolved stays visible for review


def test_policy_change_changes_hash():  # RISK-003
    changed = AnalysisConfig(CFG.detectors, {**POLICY, "alert_min_band": "high"})
    assert changed.config_sha256 != CFG.config_sha256 and changed.policy_sha256 != CFG.policy_sha256


def _transfers(dataset_id, rows):
    records, _ = prepare_batch(list(enumerate(rows, 1)), source_id="s", is_synthetic=True)
    return [
        ObservedTransfer(
            transaction_uuid(dataset_id, r.source_id, r.source_transaction_id),
            r.source_transaction_id,
            r.sender_account_id,
            r.receiver_account_id,
            r.amount_minor,
            r.currency,
            r.observed_date,
            r.occurred_at,
            r.time_precision,
            r.status,
        )
        for r in records
    ]


def test_pipeline_is_deterministic_under_row_reordering():  # DATA-003, FORM determinism
    ds = generate("demo-v1", 7)
    rows = ds.rows[:]
    a = run_analysis(dataset_id="d", transfers=_transfers("d", rows), contract=ds.coverage_contract, config=CFG)
    random.Random(3).shuffle(rows)
    b = run_analysis(dataset_id="d", transfers=_transfers("d", rows), contract=ds.coverage_contract, config=CFG)
    assert a.snapshot_id == b.snapshot_id
    assert [f.id for f in a.formations] == [f.id for f in b.formations]
    assert [(x.id, x.provenance_hash) for x in a.evidence] == [(x.id, x.provenance_hash) for x in b.evidence]
    assert [(x.id, x.band, x.priority) for x in a.assessments] == [(x.id, x.band, x.priority) for x in b.assessments]


def _member_family(ds, out):
    owner = {acc: t for t in ds.truth for acc in t.accounts}
    result = {}
    for f in out.formations:
        fams = {owner[m].family for m in f.member_ids if m in owner}
        if len(fams) == 1:
            result.setdefault(fams.pop(), []).append(f)
    return result


@pytest.mark.parametrize("seed", [2026, 11, 404])
def test_demo_suite_behaviour(seed):
    ds = generate("demo-v1", seed)
    out = run_analysis(dataset_id="d", transfers=_transfers("d", ds.rows), contract=ds.coverage_contract, config=CFG)
    assert out.quarantined == []
    risk = {a.formation_id: a for a in out.assessments}
    by_family = _member_family(ds, out)
    funnel = [f for f in by_family["S1_collection_funnel"] if f.kind == "funnel"]
    assert funnel and risk[funnel[0].id].band == "high"
    chain = [f for f in by_family["S2_layering_chain"] if f.kind == "chain"]
    assert chain and risk[chain[0].id].band == "high"
    same_day = [f for f in by_family["H_same_day_chain"] if f.kind == "chain"]
    assert same_day and risk[same_day[0].id].band == "medium"  # ambiguous chronology never reaches high
    assert all(risk[f.id].band == "low" for f in by_family.get("N8_reverse_chronology_chain", []))  # FORM-003
    boundary = [f for f in by_family["S1_collection_funnel_boundary"] if f.kind == "funnel"]
    assert boundary and risk[boundary[0].id].band == "insufficient_evidence"  # COVER-001
    assert not any(f.kind == "funnel" for f in by_family.get("N1_payroll", []))  # FORM-002: fan-out is not a funnel


def test_all_published_evidence_resolves_and_recomputes():  # EVID-001, EVID-003
    ds = generate("demo-v1", 2026)
    transfers = _transfers("d", ds.rows)
    out = run_analysis(dataset_id="d", transfers=transfers, contract=ds.coverage_contract, config=CFG)
    by_id = {t.transaction_id: t for t in transfers}
    for ev in out.evidence:
        validate_evidence(ev, by_id)


def test_broken_evidence_is_rejected():  # EVID-002
    transfers = {t.transaction_id: t for t in [tx("1", "A", "B", 100)]}
    ev = Evidence("e", "graph_fact", "X", "f", ("1", "missing"), (), {"total_minor": "100"}, {}, (), "v")
    with pytest.raises(EvidenceIntegrityError):
        validate_evidence(ev, transfers)
    wrong_sum = dataclasses.replace(ev, transaction_ids=("1",), observations={"total_minor": "101"})
    with pytest.raises(EvidenceIntegrityError):
        validate_evidence(wrong_sum, transfers)


def test_generator_is_deterministic_and_label_free():  # BENCH-001, BENCH-002
    a, b = generate("demo-v1", 99), generate("demo-v1", 99)
    assert a.manifest_sha256 == b.manifest_sha256 and a.truth_sha256 == b.truth_sha256
    assert generate("demo-v1", 100).manifest_sha256 != a.manifest_sha256
    allowed = {
        "source_transaction_id",
        "sender_account_id",
        "receiver_account_id",
        "amount_minor",
        "currency",
        "observed_date",
        "occurred_at",
        "status",
    }
    assert all(set(r) == allowed for r in a.rows)
    for suite in SUITES:
        contract = generate(suite, 1).coverage_contract
        assert not ({"label", "family", "scenario_id", "is_fraud"} & set(contract))
