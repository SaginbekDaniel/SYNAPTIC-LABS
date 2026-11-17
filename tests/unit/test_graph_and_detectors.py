import random

from nexora.analytics.config import default_config
from nexora.analytics.graph_builder import build_snapshot, input_manifest_sha256
from nexora.analytics.structural.chain import detect_chains
from nexora.analytics.structural.funnel import detect_funnels
from tests.helpers import tx

CFG = default_config().detectors


def test_aggregate_conservation_and_policy():  # GRAPH-001
    txs = [
        tx("1", "A", "B", 100),
        tx("2", "A", "B", 250, 1),
        tx("3", "B", "C", 70, 2),
        tx("4", "A", "B", 999, 3, status="reversed"),
        tx("5", "C", "C", 40, 3),  # self-transfer
    ]
    snap = build_snapshot(txs)
    cg = snap.by_currency["KZT"]
    assert cg.edges[("A", "B")].amount_minor == 350 and cg.edges[("A", "B")].n_transactions == 2
    eligible_non_self = 100 + 250 + 70
    assert sum(e.amount_minor for e in cg.edges.values()) == eligible_non_self
    assert snap.excluded_count == 1
    assert cg.metrics["C"].self_transfer_count == 1
    assert not cg.graph.has_edge("C", "C")


def test_self_transfer_only_account_is_an_isolate():  # GRAPH-003
    snap = build_snapshot([tx("1", "A", "B", 10), tx("2", "Z", "Z", 10)])
    g = snap.by_currency["KZT"].graph
    assert "Z" in g and g.degree("Z") == 0


def test_manifest_is_order_independent():  # DATA-003
    txs = [tx(str(i), f"A{i % 5}", f"B{i % 7}", 100 + i, i % 9) for i in range(40)]
    shuffled = txs[:]
    random.Random(1).shuffle(shuffled)
    assert input_manifest_sha256(txs) == input_manifest_sha256(shuffled)


def _funnel_txs(n_feeders: int, *, center: str = "C"):
    return [tx(f"f{i}", f"F{i}", center, 2_000_000, i % 2) for i in range(n_feeders)]


def test_funnel_three_feeders():  # FORM-001
    found = detect_funnels(build_snapshot(_funnel_txs(3)).by_currency["KZT"], CFG["funnel"])
    assert len(found) == 1 and found[0].center == "C"
    assert found[0].total_incoming_minor == 6_000_000
    assert {f.share_bp for f in found[0].feeders} == {10_000}


def test_funnel_needs_distinct_feeders_and_share():
    snap = build_snapshot([*_funnel_txs(2), tx("x", "C", "C", 5000000)])  # self-loop must not count as a feeder
    assert detect_funnels(snap.by_currency["KZT"], CFG["funnel"]) == []
    # A sender routing only a small share of its outflow to C is not a feeder.
    low_share = [*_funnel_txs(2), tx("y", "F9", "C", 2000000), tx("z", "F9", "Q", 9000000)]
    assert detect_funnels(build_snapshot(low_share).by_currency["KZT"], CFG["funnel"]) == []


def test_direction_reversal_changes_detection():  # GRAPH-002
    reversed_txs = [tx(f"f{i}", "C", f"F{i}", 2_000_000) for i in range(4)]  # fan-out, not funnel
    assert detect_funnels(build_snapshot(reversed_txs).by_currency["KZT"], CFG["funnel"]) == []


def _chain(path, amounts, days):
    return [tx(f"h{i}", path[i], path[i + 1], amounts[i], days[i]) for i in range(len(path) - 1)]


def test_chain_detects_maximal_path_only():
    det = detect_chains(build_snapshot(_chain("ABCDE", [5_000_000] * 4, [0, 1, 2, 3])).by_currency["KZT"], CFG["chain"])
    assert [c.path for c in det.candidates] == [tuple("ABCDE")]
    assert not det.budget_exceeded


def test_chain_requires_consistent_hop_amounts():
    det = detect_chains(
        build_snapshot(_chain("ABCD", [5_000_000, 5_000_000, 1_100_000], [0, 1, 2])).by_currency["KZT"],
        CFG["chain"],
    )
    assert det.candidates == ()


def test_chain_budget_fails_closed():  # GRAPH-004
    # Dense layered graph: many paths; tiny budget must stop enumeration and flag it.
    txs = []
    n = 0
    for layer in range(4):
        for a in range(3):
            for b in range(3):
                txs.append(tx(f"t{n}", f"L{layer}-{a}", f"L{layer + 1}-{b}", 3_000_000, layer))
                n += 1
    cfg = {**CFG["chain"], "max_expansions": 10, "intermediary_max_degree": 10}
    det = detect_chains(build_snapshot(txs).by_currency["KZT"], cfg)
    assert det.budget_exceeded and det.expansions <= 11
