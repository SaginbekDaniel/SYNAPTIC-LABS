"""Regression tests for every confirmed v1 false-positive root cause and the v2 detectors.

Each test builds the smallest transfer set that exhibits one mechanism from
docs/FRAUD_FAILURE_ANALYSIS.md, so a regression points at the cause, not at a benchmark score.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from nexora.analytics import attribution
from nexora.analytics.config import CONFIG_DIR, load_config
from nexora.analytics.evidence_validation import validate_evidence
from nexora.analytics.graph_builder import build_snapshot
from nexora.analytics.pipeline import AnalysisOutput, run_analysis
from nexora.analytics.structural.cycle import detect_cycles
from nexora.analytics.structural.funnel import dedication_strength, funnel_strength
from nexora.domain.transfers import ObservedTransfer
from tests.helpers import tx

V1 = load_config(CONFIG_DIR / "v1")
V2 = load_config(CONFIG_DIR)
CONTRACT: dict[str, object] = {"boundary_account_ids": [], "upstream_observed": True}
M = 100  # tiyn per tenge


def run(transfers: list[ObservedTransfer], config=V2, contract=CONTRACT) -> AnalysisOutput:  # type: ignore[no-untyped-def]
    out = run_analysis(dataset_id="t", transfers=transfers, contract=dict(contract), config=config)
    assert out.quarantined == []
    return out


def by_kind(out: AnalysisOutput, kind: str, subject: str):  # type: ignore[no-untyped-def]
    formations = {f.id: f for f in out.formations}
    hits = [
        a
        for a in out.assessments
        if formations[a.formation_id].kind == kind and formations[a.formation_id].subject_account_id == subject
    ]
    assert hits, f"no {kind} formation on {subject}"
    return hits[0]


def temporal(out: AnalysisOutput, formation_id: str):  # type: ignore[no-untyped-def]
    return next(s for s in out.signals if s.formation_id == formation_id and s.family == "TEMPORAL")


def mule_funnel(prefix: str = "m", feeders: int = 5) -> list[ObservedTransfer]:
    rows = [tx(f"{prefix}f{i}", f"{prefix}F{i}", f"{prefix}C", 400_000 * M, day=10 + i % 3) for i in range(feeders)]
    rows.append(tx(f"{prefix}o", f"{prefix}C", f"{prefix}X", 400_000 * M * feeders * 95 // 100, day=14))
    return rows


def merchant_hub() -> list[ObservedTransfer]:
    """16 repeat customers; the processor settles every 3 days to the same 4 merchants."""
    rows: list[ObservedTransfer] = []
    n = 0
    for day in range(30):
        for c in range(16):
            if (day + c) % 5 == 0:
                rows.append(tx(f"h{n}", f"cust{c}", "PROC", 20_000 * M + c * M, day=day))
                n += 1
        if day % 3 == 2:
            for m in range(4):
                rows.append(tx(f"h{n}", "PROC", f"merch{m}", 70_000 * M, day=day))
                n += 1
    return rows


# -- root cause 1: structural strength rewarded feeder count --------------------------------


def test_funnel_strength_does_not_grow_with_feeder_count() -> None:
    assert funnel_strength(16, 3) > funnel_strength(5, 3)  # the v1 heuristic, kept for configs/v1
    assert dedication_strength([10_000] * 5, "0.5") == dedication_strength([10_000] * 16, "0.5") == 1.0
    assert dedication_strength([5_000] * 9, "0.5") == 0.6


# -- root causes 2+3: hubs pass the temporal test by design; no counter-evidence ------------


def test_merchant_hub_is_explained_by_benign_context_and_ranked_below_mule_funnel() -> None:
    out_v1 = run(merchant_hub() + mule_funnel(), V1)
    hub_v1, mule_v1 = by_kind(out_v1, "funnel", "PROC"), by_kind(out_v1, "funnel", "mC")
    assert hub_v1.band == "high" and hub_v1.priority > mule_v1.priority  # the documented v1 failure

    out = run(merchant_hub() + mule_funnel())
    hub, mule = by_kind(out, "funnel", "PROC"), by_kind(out, "funnel", "mC")
    benign = next(r for r in hub.reason_codes if r.code == "BENIGN_CONTEXT")
    assert set(benign.params["indicators"]) >= {"CTX_RECURRING_RELATIONSHIPS", "CTX_SCHEDULED_PAYOUTS"}
    assert hub.band == "low"  # two independent indicators: no alert, still assessed and auditable
    assert mule.band == "high" and not any(r.code == "BENIGN_CONTEXT" for r in mule.reason_codes)
    ctx = [e for e in out.evidence if e.subject_id == hub.formation_id and e.kind == "counterevidence"]
    assert {e.reason_code for e in ctx} >= {"CTX_RECURRING_RELATIONSHIPS", "CTX_SCHEDULED_PAYOUTS"}
    assert all(e.transaction_ids for e in ctx)  # every counter-indicator is verifiable


# -- new root cause found on dev: pass-through credited from a subset of the inflow ---------


def test_shop_payout_funded_by_other_customers_is_not_attributed_to_feeders() -> None:
    rows = [tx(f"q{i}", f"Q{i}", "SHOP", 20_000 * M, day=3) for i in range(3)]  # 3 dedicated feeders
    rows += [tx(f"o{i}", f"walkin{i % 7}", "SHOP", 20_000 * M, day=2 + i % 4) for i in range(40)]
    rows += [tx(f"w{i}", f"walkin{i % 7}", f"elsewhere{i}", 30_000 * M, day=1) for i in range(40)]
    rows.append(tx("sup", "SHOP", "SUPPLIER", 200_000 * M, day=6))
    a_v1 = by_kind(run(rows, V1), "funnel", "SHOP")
    out = run(rows)
    a = by_kind(out, "funnel", "SHOP")
    assert temporal(run(rows, V1), a_v1.formation_id).status == "supported"  # v1 credits the whole payout
    t = temporal(out, a.formation_id)
    assert t.status == "contradicted" and "funds_diluted_by_other_activity" in t.limitations
    assert a.band == "low"


# -- background chain root causes: busy intermediary, opening balance -----------------------


def test_coincidental_chain_through_busy_intermediary_is_not_supported() -> None:
    rows = [
        tx("h0", "A", "B", 103_935 * M, day=12),
        tx("h1", "B", "C", 103_439 * M, day=15),
        tx("h2", "C", "D", 99_652 * M, day=18),
        # B: one more inflow, three more payees, and pays out ~1.9x what it received
        tx("b1", "P", "B", 86_000 * M, day=2),
        tx("b2", "B", "Q1", 90_000 * M, day=4),
        tx("b3", "B", "Q2", 90_000 * M, day=20),
        tx("b4", "B", "Q3", 80_000 * M, day=22),
        tx("c1", "C", "R1", 66_000 * M, day=25),
    ]
    a_v1 = next(a for a in run(rows, V1).assessments if a.band == "high")
    assert a_v1  # v1: high
    out = run(rows)
    snapshot = build_snapshot(rows)
    assert attribution.path_pro_rata(snapshot.by_currency["KZT"], ("A", "B", "C", "D")) * 2 < 103_935 * M
    assert all(a.band in ("low", "insufficient_evidence") for a in out.assessments)


def test_dedicated_layering_chain_stays_supported_under_attribution() -> None:
    rows = [
        tx("l0", "A", "B", 1_000_000 * M, day=1),
        tx("l1", "B", "C", 980_000 * M, day=2),
        tx("l2", "C", "D", 960_000 * M, day=3),
        tx("n1", "B", "noise", 5_000 * M, day=9),
    ]
    out = run(rows)
    a = by_kind(out, "chain", "D")
    assert a.band == "high" and temporal(out, a.formation_id).status == "supported"


def test_pro_rata_bounds_are_exact_integers() -> None:
    cg = build_snapshot(
        [tx("a", "X", "H", 300, 0), tx("b", "Y", "H", 700, 0), tx("c", "H", "Z", 500, 1), tx("d", "H", "W", 600, 2)]
    ).by_currency["KZT"]
    assert attribution.funding(cg, "H") == 1100  # paid out more than received: opening balance counts
    assert attribution.consolidation_pro_rata(cg, "H", 300) == 1100 * 300 // 1100 == 300
    assert attribution.path_pro_rata(cg, ("X", "H", "Z")) == 500 * 300 // 1100


# -- fan-out ---------------------------------------------------------------------------------


def _distribution(onward: bool, boundary: bool = False) -> tuple[list[ObservedTransfer], dict[str, object]]:
    rows = [tx("fund", "FUNDER", "S", 3_000_000 * M, day=1)]
    for i in range(6):
        rows.append(tx(f"d{i}", "S", f"R{i}", 450_000 * M, day=2))
        if onward:
            rows.append(tx(f"e{i}", f"R{i}", "EXIT", 430_000 * M, day=3))
        else:  # payroll-like: small purchases spread over the month
            rows += [tx(f"s{i}-{k}", f"R{i}", f"shop{k}", 15_000 * M, day=4 + 3 * k) for k in range(8)]
    contract = {**CONTRACT, "boundary_account_ids": [f"R{i}" for i in range(6)] if boundary else []}
    return rows, contract


def test_fanout_with_rapid_onward_movement_is_high() -> None:
    rows, contract = _distribution(onward=True)
    out = run(rows, contract=contract)
    a = by_kind(out, "fanout", "S")
    assert a.band == "high" and temporal(out, a.formation_id).status == "supported"
    assert not any(f.kind == "fanout" for f in run(rows, V1).formations)  # v1 has no such detector


def test_payroll_like_fanout_without_onward_movement_is_not_alerted() -> None:
    rows, contract = _distribution(onward=False)
    a = by_kind(run(rows, contract=contract), "fanout", "S")
    assert a.band == "low"


def test_fanout_with_recipients_at_boundary_abstains() -> None:
    rows, contract = _distribution(onward=False, boundary=True)
    rows = [r for r in rows if not r.sender.startswith("R")]  # beyond the boundary nothing is observed
    a = by_kind(run(rows, contract=contract), "fanout", "S")
    assert a.band == "insufficient_evidence" and a.priority is None


# -- cycles ----------------------------------------------------------------------------------


def _ring(rounds: int, *, consistent: bool = True) -> list[ObservedTransfer]:
    rows = []
    for r in range(rounds):
        amount = 500_000 * M + r * 37_000 * M
        for leg, (s, t) in enumerate((("A", "B"), ("B", "C"), ("C", "A"))):
            value = amount - leg * 5_000 * M if consistent else amount * (leg + 1) // 2
            rows.append(tx(f"r{r}-{leg}", s, t, value, day=1 + 7 * r + leg))
    return rows


def test_repeated_round_trips_are_supported_and_one_off_is_not() -> None:
    out = run(_ring(3))
    cycles = [a for a in out.assessments if any(f.id == a.formation_id and f.kind == "cycle" for f in out.formations)]
    assert len(cycles) == 1 and cycles[0].band == "high"  # one ring, not one per rotation
    one = run(_ring(1))
    single = [f for f in one.formations if f.kind == "cycle"]
    assert single and temporal(one, single[0].id).status == "contradicted"


def test_amount_inconsistent_mutual_invoicing_is_not_a_round_trip() -> None:
    out = run(_ring(3, consistent=False))
    f = next(f for f in out.formations if f.kind == "cycle")
    assert temporal(out, f.id).status == "contradicted"


def test_cycle_enumeration_fails_closed_under_budget() -> None:
    rows = [tx(f"k{i}-{j}", f"N{i}", f"N{j}", 2_000_000 * M, day=1) for i in range(7) for j in range(7) if i != j]
    det = detect_cycles(build_snapshot(rows).by_currency["KZT"], {**V2.detectors["cycle"], "max_expansions": 20})
    assert det.budget_exceeded


def test_all_v2_evidence_validates() -> None:
    rows = merchant_hub() + mule_funnel() + _ring(3) + _distribution(onward=True)[0]
    out = run(rows)
    for ev in out.evidence:
        validate_evidence(ev, out.snapshot.transfers)
    assert {f.kind for f in out.formations} >= {"funnel", "fanout", "cycle"}


# -- the documented demo dataset ------------------------------------------------------------


def test_demo_dataset_v2_ranks_planted_funnel_above_merchant_hub_and_drops_background_chain() -> None:
    path = Path(__file__).resolve().parents[2] / "scripts" / "trace_v1_false_positives.py"
    spec = importlib.util.spec_from_file_location("trace_v1", path)
    assert spec and spec.loader
    trace = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trace)
    ds, transfers = trace.load("demo-v1", 2026)
    out = run(transfers, contract=ds.coverage_contract)
    truth = {s.family: set(s.accounts) for s in ds.truth}
    formations = {f.id: f for f in out.formations}

    def best(family: str):  # type: ignore[no-untyped-def]
        return max(
            (a for a in out.assessments if set(formations[a.formation_id].member_ids) & truth[family]),
            key=lambda a: a.priority or -1,
        )

    hub, mule = best("N2_merchant_settlement"), best("S1_collection_funnel")
    assert mule.band == "high" and hub.band == "low"
    scenario = set().union(*truth.values())
    assert not any(
        a.band in ("high", "critical")
        for a in out.assessments
        if not set(formations[a.formation_id].member_ids) & scenario
    )
