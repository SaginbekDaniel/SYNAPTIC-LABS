"""Frozen synthetic protocol for evaluating contextual evidence with and without receipts."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nexora.analytics.config import default_config, experimental_config
from nexora.analytics.context import VerifiedContext, VerifiedFact
from nexora.analytics.pipeline import run_analysis
from nexora.domain.ids import canonical_json, sha256_hex
from nexora.domain.transfers import ObservedTransfer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from fraud_experiment import BANDS, metrics

PROTOCOL = "synthetic-context-v1"
SEEDS = {"development": (1229, 1283), "calibration": (2251, 2267), "holdout": (3319, 3323, 3359)}
PERIODS = {"development": 1, "calibration": 4, "holdout": 8}
TEMPLATES = ("two_stage", "branching", "returned_principal", "isolated")


def ledger(seed, month, prevalence):
    rng = random.Random(seed)
    cutoff = datetime(2026, month, 25, tzinfo=UTC)
    day = cutoff - timedelta(days=14)
    positive = set(rng.sample(range(48), round(48 * prevalence)))
    transactions, facts, families = [], [], {}
    truth = {"network": {}, "transaction": {}, "account": {}}
    for index in range(48):
        family = TEMPLATES[index % len(TEMPLATES)]
        group = f"case{index:02}"
        amount = rng.randrange(2_400_000, 6_400_000)

        def node(suffix, group=group):
            return f"{group}:{suffix}"

        edges = {
            "two_stage": [("issuer", "partner"), ("partner", "broker"), ("broker", "end")],
            "branching": [("capital", "center"), *(("center", f"member{i}") for i in range(6))],
            "returned_principal": [("alpha", "beta"), ("beta", "gamma"), ("gamma", "alpha")],
            "isolated": [("sender", "receiver"), ("sender", "receiver")],
        }[family]
        names = sorted({item for edge in edges for item in edge})
        truth["network"][group] = index in positive
        families[group] = family
        for name in names:
            truth["account"][node(name)] = index in positive
        identifiers = set()
        occurred = day + timedelta(hours=index % 9)
        for position, (sender, receiver) in enumerate(edges):
            ident = f"{group}:tx{position}"
            identifiers.add(ident)
            occurred = occurred + timedelta(minutes=rng.randint(2, 75))
            movement = amount * 7 if family == "branching" and position == 0 else amount
            transactions.append(
                ObservedTransfer(
                    ident, ident, node(sender), node(receiver), movement, "KZT", occurred.date(), occurred, "timestamp"
                )
            )
            truth["transaction"][ident] = index in positive

        # Separate synthetic evidence channel. Some benign cases have no receipt,
        # some receipts arrive too late, and reports exist for only some fraud cases.
        observed = rng.random()
        if index in positive and observed < 0.4:
            kind, when = "confirmed_fraud_report", cutoff - timedelta(hours=3)
        elif index not in positive and observed < 0.8:
            kind = "verified_business_activity"
            when = cutoff + timedelta(days=1) if observed > 0.65 else cutoff - timedelta(hours=3)
        else:
            continue
        for name in names:
            facts.append(
                VerifiedFact(
                    source_ref=f"synthetic-ledger/{seed}/{group}/{name}",
                    kind=kind,
                    subject=node(name),
                    currency="KZT",
                    observed_at=occurred,
                    known_at=when,
                    valid_until=cutoff + timedelta(days=7),
                    source_transaction_ids=frozenset(identifiers),
                )
            )
    return transactions, VerifiedContext(as_of=cutoff, facts=tuple(facts)), truth, families


def evaluate(transactions, context, truth, families, config):
    start = time.perf_counter()
    out = run_analysis(
        dataset_id="frozen-context-study", transfers=transactions, contract={}, config=config, context=context
    )
    elapsed = (time.perf_counter() - start) * 1000
    formations = {row.id: row for row in out.formations}
    scores = {unit: defaultdict(int) for unit in truth}
    flags = {unit: set() for unit in truth}
    for row in out.assessments:
        formation = formations[row.formation_id]
        subject = formation.subject_account_id
        ids = {"network": (subject.split(":")[0],), "account": (subject,), "transaction": formation.transaction_ids}
        for unit, entities in ids.items():
            for entity in entities:
                scores[unit][entity] = max(scores[unit][entity], row.priority or 0)
                if row.band in BANDS:
                    flags[unit].add(entity)
    results = {unit: metrics(labels, scores[unit], flags[unit], 10) for unit, labels in truth.items()}
    results["scenario"] = results["network"]  # one disconnected planted graph per scenario
    results["per_typology"] = {}
    for family in TEMPLATES:
        labels = {key: value for key, value in truth["network"].items() if families[key] == family}
        results["per_typology"][family] = metrics(labels, scores["network"], flags["network"] & labels.keys(), 10)
    results["latency_ms"] = elapsed
    results["alerts"] = sum(row.band in BANDS for row in out.assessments)
    results["formations"] = len(out.formations)
    results["abstentions"] = sum(row.priority is None for row in out.assessments)
    results["context_coverage"] = sum("NETWORK_CONTEXT" not in row.missing_families for row in out.assessments)
    results["coverage"] = not out.partial_reasons
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    runs = []
    for split, seeds in SEEDS.items():
        for seed in seeds:
            for prevalence in (0.05, 0.20):
                rows, context, truth, families = ledger(seed, PERIODS[split], prevalence)
                without = VerifiedContext(as_of=context.as_of, facts=())
                input_hash = sha256_hex(
                    canonical_json(
                        [
                            [
                                [
                                    row.source_transaction_id,
                                    row.sender,
                                    row.receiver,
                                    row.amount_minor,
                                    row.occurred_at.isoformat(),
                                ]
                                for row in rows
                            ],
                            context.manifest(),
                            truth,
                            families,
                        ]
                    )
                )
                runs.append(
                    {
                        "split": split,
                        "seed": seed,
                        "prevalence": prevalence,
                        "manifest": input_hash,
                        "v2": evaluate(rows, context, truth, families, default_config()),
                        "v3_without_context": evaluate(rows, without, truth, families, experimental_config()),
                        "v3": evaluate(rows, context, truth, families, experimental_config()),
                    }
                )
    args.output.write_text(json.dumps({"protocol": PROTOCOL, "runs": runs}, indent=2) + "\n")


if __name__ == "__main__":
    main()
