"""Regression tests for defects found in the deep audit (docs/architecture/ROOT_CAUSE_FIXES.md).

Each test was written first, observed failing on the pre-audit code, and documents one
root cause. Metamorphic tests at the end pin invariants the pipeline must keep.
"""

from __future__ import annotations

import dataclasses

from nexora.analytics.config import default_config
from nexora.analytics.graph_builder import build_snapshot
from nexora.analytics.pipeline import run_analysis
from nexora.analytics.structural.funnel import detect_funnels
from nexora.ingest.validation import RowIssue, parse_record
from tests.helpers import tx

CFG = default_config()
M = 1_000_000_00
CONTRACT = {"boundary_account_ids": [], "upstream_observed": True}


def _row(**over: str) -> dict[str, str]:
    base = {
        "source_transaction_id": "t1",
        "sender_account_id": "A",
        "receiver_account_id": "B",
        "amount_minor": "100",
        "currency": "KZT",
        "observed_date": "2026-07-10",
        "occurred_at": "",
    }
    return {**base, **over}


# -- RC-01: contradictory date and timestamp -------------------------------------------------
def test_observed_date_contradicting_timestamp_is_quarantined() -> None:
    """A row whose posting date lies 9 days from its own timestamp has no defensible chronology:
    ordering would use the timestamp while lags use the date."""
    r = parse_record(_row(occurred_at="2026-07-01T10:00:00Z"), row_number=1, source_id="s", is_synthetic=False)
    assert isinstance(r, RowIssue)
    assert r.code == "DATE_TIMESTAMP_MISMATCH"


def test_one_day_timezone_offset_between_date_and_timestamp_is_accepted() -> None:
    # 23:30 local (UTC+5) on the 10th is 18:30 UTC on the 10th; 02:00 local on the 11th is the 10th in UTC.
    r = parse_record(_row(occurred_at="2026-07-11T02:00:00+05:00"), row_number=1, source_id="s", is_synthetic=False)
    assert not isinstance(r, RowIssue)


# -- RC-02: returning-feeder rule evaded by token "activation" payments ---------------------
def _funnel_with_activation(activation_pct: int):
    """Centre first pays each feeder a token amount, then collects ~10x that from each feeder."""
    txs = []
    for i in range(5):
        txs.append(tx(f"act{i}", "C", f"F{i}", 3 * M * activation_pct // 100, 0))
        txs.append(tx(f"in{i}", f"F{i}", "C", 3 * M, 2))
    txs.append(tx("out", "C", "X", 14 * M, 3))
    return txs


def test_token_activation_payments_do_not_erase_a_collection_funnel() -> None:
    """Pre-audit: any centre->feeder payment >= 10% of the feeder's transfer reclassified the feeder as
    'returning funds', so paying each mule 10% made the whole funnel disappear (fail-open evasion).
    A loan repayment cannot exceed the loan it repays several times over."""
    snap = build_snapshot(_funnel_with_activation(10))
    found = detect_funnels(snap.by_currency["KZT"], CFG.detectors["funnel"])
    assert [c.center for c in found] == ["C"]
    assert len(found[0].feeders) == 5


def test_genuine_instalments_are_still_returning_feeders() -> None:
    """Borrowers repay 20-35% of a larger principal: still not independent feeders."""
    txs = []
    for i in range(5):
        txs.append(tx(f"loan{i}", "C", f"F{i}", 10 * M, 0))
        txs.append(tx(f"inst{i}", f"F{i}", "C", 3 * M, 12))
    snap = build_snapshot(txs)
    assert detect_funnels(snap.by_currency["KZT"], CFG.detectors["funnel"]) == []


# -- Metamorphic invariants ----------------------------------------------------------------
def _scenario():
    txs = [tx(f"in{i}", f"F{i}", "C", 3 * M + i, 1 + i % 2) for i in range(5)]
    txs += [tx("out1", "C", "X", 8 * M, 4), tx("out2", "C", "Y", 6 * M, 5)]
    txs += [tx(f"b{i}", f"P{i}", f"Q{i}", M // 10, i) for i in range(10)]
    return txs


def _summary(out):
    risk = {a.formation_id: a for a in out.assessments}
    return sorted((f.kind, f.subject_account_id, risk[f.id].band, risk[f.id].priority) for f in out.formations)


def test_row_order_does_not_change_results() -> None:
    txs = _scenario()
    a = run_analysis(dataset_id="d", transfers=txs, contract=CONTRACT, config=CFG)
    b = run_analysis(dataset_id="d", transfers=list(reversed(txs)), contract=CONTRACT, config=CFG)
    assert [f.id for f in a.formations] == [f.id for f in b.formations]
    assert _summary(a) == _summary(b)


def test_renaming_accounts_does_not_change_topology_judgements() -> None:
    txs = _scenario()
    rename = {a: f"zz{a}" for t in txs for a in (t.sender, t.receiver)}
    renamed = [dataclasses.replace(t, sender=rename[t.sender], receiver=rename[t.receiver]) for t in txs]
    a = run_analysis(dataset_id="d", transfers=txs, contract=CONTRACT, config=CFG)
    b = run_analysis(dataset_id="d", transfers=renamed, contract=CONTRACT, config=CFG)
    strip = lambda out: sorted((k, band, prio) for k, _, band, prio in _summary(out))  # noqa: E731
    assert strip(a) == strip(b)


def test_currency_labels_never_merge_flows() -> None:
    """Half of the feeders in another currency: no single-currency funnel has 5 feeders."""
    txs = _scenario()
    mixed = [dataclasses.replace(t, currency="USD") if t.transaction_id in {"in0", "in1", "in2"} else t for t in txs]
    out = run_analysis(dataset_id="d", transfers=mixed, contract=CONTRACT, config=CFG)
    for f in out.formations:
        currencies = {t.currency for t in mixed if t.transaction_id in f.transaction_ids}
        assert currencies == {f.currency}


def test_removing_evidence_never_strengthens_the_assessment() -> None:
    """Dropping the onward leg removes temporal support; the band must not rise."""
    order = ["low", "medium", "high", "critical"]
    full = run_analysis(dataset_id="d", transfers=_scenario(), contract=CONTRACT, config=CFG)
    fewer = run_analysis(
        dataset_id="d",
        transfers=[t for t in _scenario() if not t.transaction_id.startswith("out")],
        contract=CONTRACT,
        config=CFG,
    )
    band = lambda out: max(  # noqa: E731
        (order.index(a.band) for a in out.assessments if a.band in order), default=-1
    )
    assert band(fewer) <= band(full)
