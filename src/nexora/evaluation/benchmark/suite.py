"""Benchmark suite assembly: families, network instances, splits and provenance.

A *network* is the unit of independence: one planted scenario plus its own background
population, observation window and time precision. Splits are assigned per network from
disjoint seed spaces, so no account, transaction or scenario instance appears in two splits.

Labels are returned as ``TruthRecord`` objects next to — never inside — the detector input.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from nexora.domain.ids import canonical_json, sha256_hex
from nexora.evaluation.benchmark import scenarios as sc

BENCHMARK_VERSION = "nexora-bench-v1"
Split = Literal["dev", "val", "test"]
SPLITS: tuple[Split, ...] = ("dev", "val", "test")
#: Networks generated per family and split (frozen with the benchmark version).
DEFAULT_COUNTS: dict[Split, int] = {"dev": 12, "val": 8, "test": 12}

Builder = Callable[[sc.Net], tuple[str, sc.Difficulty, sc.Expected, list[str], str]]


@dataclass(frozen=True)
class Family:
    name: str
    label: sc.Label
    group: Literal["suspicious", "benign", "hard_negative"]
    builder: Builder
    description: str


FAMILIES: tuple[Family, ...] = (
    Family(
        "P1_mule_collection",
        "suspicious",
        "suspicious",
        sc.p1_mule_collection,
        "Money-mule collection and consolidation",
    ),
    Family("P2_layering_chain", "suspicious", "suspicious", sc.p2_layering_chain, "Layered transfer chains"),
    Family(
        "P3_coordinated_distribution",
        "suspicious",
        "suspicious",
        sc.p3_coordinated_distribution,
        "Coordinated distribution to mule recipients",
    ),
    Family(
        "P4_circular_transfers", "suspicious", "suspicious", sc.p4_circular_transfers, "Repeated circular transfers"
    ),
    Family(
        "P5_split_coordinated",
        "suspicious",
        "suspicious",
        sc.p5_split_coordinated,
        "Split and coordinated transactions",
    ),
    Family("N1_merchant_settlement", "benign", "benign", sc.n1_merchant_settlement, "Merchant settlement hubs"),
    Family("N2_payroll", "benign", "benign", sc.n2_payroll, "Payroll distribution"),
    Family("N3_supplier_payments", "benign", "benign", sc.n3_supplier_payments, "Supplier payments"),
    Family("N4_family_remittance", "benign", "benign", sc.n4_family_remittance, "Family remittances"),
    Family("N5_group_reimbursement", "benign", "benign", sc.n5_group_reimbursement, "Group reimbursements"),
    Family("N6_loan_repayment", "benign", "benign", sc.n6_loan_repayment, "Loan repayment patterns"),
    Family("H1_crowdfunding", "benign", "hard_negative", sc.h1_crowdfunding, "Crowdfunding / group purchase (vs P1)"),
    Family("H2_microfinance_hub", "benign", "hard_negative", sc.h2_microfinance_hub, "Microfinance re-lending (vs P1)"),
    Family(
        "H3_tight_supplier_chain",
        "benign",
        "hard_negative",
        sc.h3_tight_supplier_chain,
        "Low-margin supply chain (vs P2)",
    ),
    Family(
        "H4_reverse_chronology_chain",
        "benign",
        "hard_negative",
        sc.h4_reverse_chronology_chain,
        "Backwards-in-time path (vs P2)",
    ),
    Family("H5_payout_sweep", "benign", "hard_negative", sc.h5_payout_sweep, "Payouts swept to savings (vs P3)"),
    Family(
        "H6_reciprocal_trading", "benign", "hard_negative", sc.h6_reciprocal_trading, "Mutual invoicing ring (vs P4)"
    ),
)
FAMILY_BY_NAME = {f.name: f for f in FAMILIES}


@dataclass(frozen=True)
class NetworkInput:
    """Everything a detection method may see. Contains no label."""

    network_id: str
    rows: tuple[dict[str, str], ...]
    coverage_contract: dict[str, Any]
    window: tuple[date, date]

    @property
    def manifest_sha256(self) -> str:
        return sha256_hex(canonical_json(sorted(canonical_json(r) for r in self.rows)))


@dataclass(frozen=True)
class Network:
    split: Split
    input: NetworkInput
    truth: sc.TruthRecord


def build_network(family: Family, split: Split, index: int, master_seed: int) -> Network:
    material = f"{BENCHMARK_VERSION}|{master_seed}|{split}|{family.name}|{index}"
    rng = random.Random(material)
    network_id = f"{split}-{family.name}-{index:03d}"
    days = rng.randint(28, 45)
    start = date(2026, 6, 1) + timedelta(days=rng.randrange(0, 90))
    net = sc.Net(rng=rng, start=start, days=days, precision="timestamp" if rng.random() < 0.5 else "day")
    variant, difficulty, expected, accounts, notes = family.builder(net)
    net.recording = False
    bg = sc.background(net, n_accounts=rng.randint(25, 90), n_transfers=rng.randint(60, 350))
    for fn in net.deferred:
        fn(net, bg)
    # Collection boundaries also occur in networks without a planted boundary, so the contract
    # does not reveal the label: some background accounts lose their outgoing observations.
    if rng.random() < 0.25:
        for acc in rng.sample(bg, k=rng.randint(1, 3)):
            net.boundary.add(acc)
    planted_boundary = set(accounts) & net.boundary
    rows = [r for r in net.rows if r["sender_account_id"] not in net.boundary - planted_boundary]
    kept = {r["source_transaction_id"] for r in rows}
    rng.shuffle(rows)  # source order carries no information
    contract = {
        "source": "synthetic",
        "generator_version": BENCHMARK_VERSION,
        "time_precision": net.precision,
        "boundary_account_ids": sorted(net.boundary),
        "upstream_observed": True,
        "declared_complete": False,
    }
    truth = sc.TruthRecord(
        network_id=network_id,
        family=family.name,
        variant=variant,
        label=family.label,
        difficulty=difficulty,
        expected=expected,
        accounts=tuple(accounts),
        transaction_ids=tuple(t for t in net.scenario_tx if t in kept),
        notes=notes,
    )
    window = (start, start + timedelta(days=days - 1))
    return Network(split, NetworkInput(network_id, tuple(rows), contract, window), truth)


@dataclass(frozen=True)
class Suite:
    version: str
    master_seed: int
    counts: dict[str, int]
    networks: tuple[Network, ...]

    def split(self, name: str) -> list[Network]:
        return [n for n in self.networks if n.split == name]

    def manifest(self) -> dict[str, Any]:
        per_split: dict[str, Any] = {}
        for s in SPLITS:
            nets = self.split(s)
            if not nets:
                continue
            per_split[s] = {
                "networks": len(nets),
                "transactions": sum(len(n.input.rows) for n in nets),
                "suspicious": sum(1 for n in nets if n.truth.label == "suspicious"),
                "benign": sum(1 for n in nets if n.truth.label == "benign"),
                "data_manifest_sha256": sha256_hex(canonical_json(sorted(n.input.manifest_sha256 for n in nets))),
                "truth_sha256": sha256_hex(canonical_json(sorted(canonical_json(n.truth.__dict__) for n in nets))),
            }
        return {
            "benchmark_version": self.version,
            "master_seed": self.master_seed,
            "networks_per_family": self.counts,
            "families": [
                {"name": f.name, "label": f.label, "group": f.group, "description": f.description} for f in FAMILIES
            ],
            "splits": per_split,
            "split_rule": "disjoint seed material per (split, family, index); one network = one scenario instance",
        }


def build_suite(
    *, master_seed: int = 2026, counts: dict[Split, int] | None = None, splits: tuple[Split, ...] = SPLITS
) -> Suite:
    counts = counts or DEFAULT_COUNTS
    networks = [build_network(f, s, i, master_seed) for s in splits for f in FAMILIES for i in range(counts[s])]
    return Suite(BENCHMARK_VERSION, master_seed, {k: counts[k] for k in splits}, tuple(networks))
