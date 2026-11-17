"""Fan-out, cycle, returning-counterparty rules, peer statistics and risk-policy-v2 gates."""

from __future__ import annotations

import dataclasses
import random

import pytest

from nexora.analytics.config import default_config
from nexora.analytics.evidence_validation import EvidenceIntegrityError, validate_evidence
from nexora.analytics.graph_builder import build_snapshot
from nexora.analytics.pipeline import run_analysis
from nexora.analytics.statistical.peer import PeerIndex
from nexora.analytics.structural.cycle import detect_cycles
from nexora.analytics.structural.fan_out import detect_fan_outs
from nexora.analytics.structural.funnel import detect_funnels
from tests.helpers import tx

CFG = default_config()
DET = CFG.detectors
M = 1_000_000_00  # 1 000 000.00 KZT in tiyn
CONTRACT = {"boundary_account_ids": [], "upstream_observed": True}


def _run(txs, contract=CONTRACT):
    return run_analysis(dataset_id="d", transfers=txs, contract=contract, config=CFG)


def _by_kind(out, kind):
    risk = {a.formation_id: a for a in out.assessments}
    return [(f, risk[f.id]) for f in out.formations if f.kind == kind]


# -- fan-out ---------------------------------------------------------------------------
def _distribution(lag_days: int, recipients: int = 6):
    txs = [tx("in", "SRC", "D", 6 * M, 0)]
    txs += [tx(f"o{i}", "D", f"R{i}", M - 10_000, lag_days) for i in range(recipients)]
    return txs


def test_fan_out_detects_distribution_and_temporal_corroborates():
    out = _run(_distribution(lag_days=1))
    [(f, a)] = _by_kind(out, "fan_out")
    assert f.subject_account_id == "D" and len(f.exit_ids) == 6 and f.entry_ids == ("SRC",)
    assert f.features["temporal_status"] == "supported"
    assert "COVERAGE_DOWNSTREAM_UNOBSERVED" in {r.code for r in a.reason_codes}  # recipients' onward flow unseen
    assert a.band in ("high", "medium")


def test_fan_out_with_late_payout_is_contradicted_and_not_alerted():  # payroll-like: funded weeks earlier
    out = _run(_distribution(lag_days=20))
    [(f, a)] = _by_kind(out, "fan_out")
    assert f.features["temporal_status"] == "contradicted"
    assert a.band == "low"


def test_fan_out_below_minimum_recipients_is_ignored():
    snap = build_snapshot(_distribution(lag_days=1, recipients=4))
    assert detect_fan_outs(snap.by_currency["KZT"], DET["fan_out"]) == []


def test_fan_out_excludes_recipients_that_pay_back():  # loan book: disbursement then instalment
    txs = [tx("in", "INV", "L", 10 * M, 0)]
    for i in range(6):
        txs.append(tx(f"d{i}", "L", f"B{i}", M, 1))
        txs.append(tx(f"r{i}", f"B{i}", "L", M // 4, 15))
    cg = build_snapshot(txs).by_currency["KZT"]
    assert detect_fan_outs(cg, DET["fan_out"]) == []
    legacy = {**DET["fan_out"], "exclude_returning_recipients": False}
    [cand] = detect_fan_outs(cg, legacy)
    assert cand.distributor == "L" and len(cand.recipients) == 6


def test_funnel_excludes_feeders_funded_by_the_centre():
    txs = []
    for i in range(4):
        txs.append(tx(f"d{i}", "L", f"B{i}", 4 * M, 0))
        txs.append(tx(f"r{i}", f"B{i}", "L", M, 10))
    cg = build_snapshot(txs).by_currency["KZT"]
    assert detect_funnels(cg, DET["funnel"]) == []
    [legacy] = detect_funnels(cg, {**DET["funnel"], "exclude_returning_feeders": False})
    assert len(legacy.feeders) == 4


def test_funnel_keeps_independent_feeders_and_reports_returning_ones():
    txs = [tx(f"f{i}", f"F{i}", "C", 2 * M, 1) for i in range(3)]
    txs += [tx("d", "C", "B", M, 0), tx("r", "B", "C", M // 2, 2)]  # B was paid first, then returns funds
    [cand] = detect_funnels(build_snapshot(txs).by_currency["KZT"], DET["funnel"])
    assert {f.account_id for f in cand.feeders} == {"F0", "F1", "F2"} and cand.returning_feeders == ("B",)


# -- cycle -----------------------------------------------------------------------------
def _loop(days):
    accounts = ["A", "B", "C"]
    return [tx(f"c{i}", accounts[i], accounts[(i + 1) % 3], 2 * M - i * 10_000, d) for i, d in enumerate(days)]


def test_time_respecting_cycle_is_supported():
    out = _run(_loop([1, 2, 3]))
    [(f, a)] = _by_kind(out, "cycle")
    assert f.member_ids == ("A", "B", "C")  # rotation starts at the earliest edge
    assert f.features["temporal_status"] == "supported"
    assert a.band in ("high", "medium")


def test_cycle_against_chronology_is_contradicted():  # graph loop, but money cannot have gone round
    out = _run(_loop([5, 3, 1]))
    [(f, a)] = _by_kind(out, "cycle")
    assert f.features["temporal_status"] == "contradicted" and a.band == "low"


def test_cycle_with_high_degree_member_is_not_a_pass_through_loop():
    txs = _loop([1, 2, 3]) + [tx(f"x{i}", "B", f"X{i}", M, 4) for i in range(5)]
    assert detect_cycles(build_snapshot(txs).by_currency["KZT"], DET["cycle"]).candidates == ()


def test_cycle_budget_fails_closed_as_partial():
    accounts = [f"N{i}" for i in range(4)]
    txs = [
        tx(f"{a}{b}", a, b, M, i % 3) for i, a in enumerate(accounts) for b in accounts if a != b
    ]  # complete digraph: many cycles
    det = detect_cycles(build_snapshot(txs).by_currency["KZT"], {**DET["cycle"], "max_cycles": 2})
    assert det.budget_exceeded and len(det.candidates) == 2


def test_chain_inside_a_detected_cycle_is_deduplicated():
    accounts = ["A", "B", "C", "D"]
    txs = [tx(f"c{i}", accounts[i], accounts[(i + 1) % 4], 2 * M, i + 1) for i in range(4)]
    out = _run(txs)
    assert len(_by_kind(out, "cycle")) == 1
    assert _by_kind(out, "chain") == []


# -- peer statistics -------------------------------------------------------------------
def _peer_world(subject_days: list[int]):
    """Subject plus 30 background accounts with spread-out activity of a similar size."""
    rng = random.Random(7)
    txs = [tx(f"s{i}", f"P{i}", "S", M, d) for i, d in enumerate(subject_days)]
    for a in range(30):
        for k in range(len(subject_days)):
            txs.append(tx(f"b{a}-{k}", f"Q{a}", f"Q{(a + 1) % 30}", M // 10, rng.randrange(0, 30)))
    return txs


def test_burst_account_is_a_peer_outlier():
    txs = _peer_world([3, 3, 4, 4, 5, 5])
    snap = build_snapshot(txs)
    res = PeerIndex(snap.by_currency["KZT"], snap.transfers, 3).assess("S", DET["peer"])
    assert res.status == "supported" and res.subject.burst_bp == 10_000
    assert res.fence_bp is not None and res.subject.burst_bp > res.fence_bp and res.strength >= 0.6


def test_steady_account_is_typical_of_peers():
    txs = _peer_world([1, 6, 11, 16, 21, 26])
    snap = build_snapshot(txs)
    res = PeerIndex(snap.by_currency["KZT"], snap.transfers, 3).assess("S", DET["peer"])
    assert res.status == "contradicted" and res.strength == 0.0


def test_peer_unavailable_without_cohort():
    txs = [tx(f"s{i}", f"P{i}", "S", M, 3) for i in range(4)]
    snap = build_snapshot(txs)
    cfg = {**DET["peer"], "fallback_all_active": False}
    res = PeerIndex(snap.by_currency["KZT"], snap.transfers, 3).assess("S", cfg)
    assert res.status == "unavailable" and res.strength is None


def test_peer_evidence_recomputes_and_tampering_is_rejected():
    txs = [*_peer_world([3, 3, 4, 4, 5, 5]), tx("o", "S", "Z", 5 * M, 6)]
    out = _run(txs)
    peer_ev = [e for e in out.evidence if "window_minor" in e.observations]
    assert peer_ev
    for ev in peer_ev:
        validate_evidence(ev, out.snapshot.transfers)
    broken = dataclasses.replace(peer_ev[0], observations={**peer_ev[0].observations, "window_minor": "1"})
    with pytest.raises(EvidenceIntegrityError):
        validate_evidence(broken, out.snapshot.transfers)


# -- risk-policy-v2 --------------------------------------------------------------------
def test_peer_counter_evidence_caps_band_with_named_gate():
    """A supported, chronology-compatible funnel whose centre turns money over steadily."""
    rng = random.Random(3)
    txs = []
    for c in range(6):
        for k in range(5):  # recurring customers spread over the month
            txs.append(tx(f"c{c}-{k}", f"CUST{c}", "HUB", M // 2, 1 + 5 * k + c % 3))
    for k in range(10):
        txs.append(tx(f"pay{k}", "HUB", f"M{k % 3}", 3 * M // 2, 2 + 3 * k))  # settles what it collects
    for a in range(30):
        for k in range(6):
            txs.append(tx(f"b{a}-{k}", f"Q{a}", f"Q{(a + 3) % 30}", M // 20, rng.randrange(0, 30)))
    out = _run(txs)
    funnels = _by_kind(out, "funnel")
    assert funnels
    _f, a = funnels[0]
    assert "PEER_TYPICAL_TURNOVER" in {r.code for r in a.reason_codes}
    capped = [r for r in a.reason_codes if r.code == "BAND_CAPPED_BY_EVIDENCE"]
    assert a.band == "medium" and capped and "peer_contradicted" in capped[0].params["gates"]


def test_v2_outputs_are_deterministic_under_row_order():
    txs = _distribution(1) + _loop([1, 2, 3]) + _peer_world([3, 3, 4, 4, 5, 5])
    shuffled = txs[:]
    random.Random(5).shuffle(shuffled)
    a, b = _run(txs), _run(shuffled)
    assert [x.id for x in a.assessments] == [x.id for x in b.assessments]
    assert [(x.band, x.priority) for x in a.assessments] == [(x.band, x.priority) for x in b.assessments]
    assert [e.provenance_hash for e in a.evidence] == [e.provenance_hash for e in b.evidence]
