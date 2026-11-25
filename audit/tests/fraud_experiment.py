"""Independent, synthetic, fixed-policy evaluation of batch graph detection."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from nexora.analytics.config import default_config
from nexora.analytics.pipeline import run_analysis
from nexora.domain.transfers import ObservedTransfer

MINUTE = 60
DAY = 1440
BASE = datetime(2026, 6, 1, tzinfo=UTC)
BANDS = {"medium", "high", "critical"}
CONTRACT = {"source": "independent_audit", "declared_complete": False}


@dataclass(frozen=True)
class Scenario:
    name: str
    fraud: bool
    rows: tuple[tuple[str, str, int, int], ...]
    limitation: str = ""


def chain(accounts, amount, gap=20):
    return tuple((a, b, amount - i * 1200, i * gap) for i, (a, b) in enumerate(pairwise(accounts)))


def collection(count=5, interval=7, cashout=True):
    rows = tuple((f"p{i}", "hub", 1_240_000 + i * 2_300, i * interval) for i in range(count))
    return rows + (("hub", "sink", 1_160_000 * count, count * interval + 4),) * cashout


def distribution(count=6):
    payouts = [("hub", f"p{i}", 1_340_000 + 1000 * i, 10 + i * 13) for i in range(count)]
    return (("source", "hub", 10_300_000, 0), *payouts)


CYCLE = chain("abca", 4_750_000)
HOP = chain("abcdef", 4_200_000)
HIDDEN = "The batch ledger lacks the signal needed to infer the true intent."
SCENARIOS = (
    Scenario("circular_transfer", True, CYCLE),
    Scenario("money_mule", True, collection()),
    Scenario("rapid_movement", True, chain("abcd", 9_200_000, 1)),
    Scenario("fan_in", True, collection(cashout=False), "No downstream transfer in the observed slice."),
    Scenario("fan_out", True, distribution()),
    Scenario("multi_hop", True, HOP),
    Scenario("structuring", True, tuple(("a", "b", 960_000 + i * 4000, i * 71) for i in range(9)), HIDDEN),
    Scenario("smurfing", True, collection(9, 139, False), "Cash deposit channel is missing."),
    Scenario(
        "behavior_change",
        True,
        (*(("a", "b", 12_000, i * DAY) for i in range(10)), ("a", "c", 18_900_000, 11 * DAY)),
        "No customer behavior model.",
    ),
    Scenario("unusual_amount", True, (("p", "q", 89_000_000, 5),), "No individual amount baseline."),
    Scenario(
        "dormant_activation",
        True,
        (("a", "b", 80_000, 0), ("a", "q", 9_900_000, 100 * DAY)),
        "Beginning of relationship and verified account state are unknown.",
    ),
    Scenario(
        "coordinated_activity",
        True,
        tuple((f"p{i}", f"q{i}", 1_111_111, 3) for i in range(12)),
        "Common actors and devices are missing.",
    ),
    Scenario("suspicious_intermediary", True, chain("abcd", 8_600_000, DAY)),
    Scenario("fraudulent_chain", True, chain("abcde", 6_320_000, 5)),
    Scenario("repeated_transfer", True, tuple(("a", "b", 3_900_000, i * DAY) for i in range(8)), HIDDEN),
    Scenario("high_risk_beneficiary", True, (("a", "b", 17_000_000, 1),), "Beneficiary reputation is absent."),
    Scenario("account_takeover", True, (("a", "b", 1_800_000, 0),), "No login, device or session telemetry."),
    Scenario("social_engineering", True, (("a", "b", 1_800_000, 0),), "No customer intent or scam report."),
    Scenario("mixed_fraud_network", True, (*CYCLE, ("l", "b", 20_000, 7), ("l", "m", 13_000, 48))),
    Scenario("unseen_cross_currency", True, chain("abcd", 3_990_000), "Alternating KZT/USD, no FX linkage."),
    Scenario("salary", False, distribution(), "Same ledger as fan-out, salary purpose is missing."),
    Scenario("family", False, (("a", "b", 1_800_000, 0),), "Same ledger as scam and takeover."),
    Scenario("business", False, HOP, "Same ledger as multi-hop, payable purpose is missing."),
    Scenario("merchant_settlement", False, collection(), "Same ledger as money mule."),
    Scenario("loan_repayments", False, collection(6, 3 * DAY, False)),
    Scenario("shared_expenses", False, tuple((f"p{i}", "hub", 95_000 + 5300 * i, i * DAY) for i in range(4))),
    Scenario("marketplace", False, distribution(), "No merchant identity or marketplace tag."),
    Scenario("high_volume_account", False, collection(10, DAY)),
    Scenario("subscriptions", False, tuple(("a", "b", 1_300_000, i * 30 * DAY) for i in range(5))),
    Scenario("refunds", False, CYCLE, "Same ledger as circular transfer, no purpose or original payment link."),
    Scenario(
        "own_accounts",
        False,
        (("a", "b", 20_000_000, 0), ("b", "a", 20_000_000, DAY)),
        "Beneficial owner relationship is missing.",
    ),
)


def materialize(scenario, group, *, scale=1.0, offset=0):
    for index, (sender, receiver, amount, minute) in enumerate(scenario.rows):
        when = BASE + timedelta(minutes=offset + minute)
        currency = "USD" if scenario.name == "unseen_cross_currency" and index % 2 else "KZT"
        tid = f"{group}:t{index}"
        yield ObservedTransfer(
            tid,
            tid,
            f"{group}:{sender}",
            f"{group}:{receiver}",
            round(amount * scale),
            currency,
            when.date(),
            when,
            "timestamp",
        )


def detect(transfers, label):
    started = time.perf_counter()
    output = run_analysis(dataset_id=label, transfers=transfers, contract=CONTRACT, config=default_config())
    latency_ms = (time.perf_counter() - started) * 1000
    formation = {item.id: item for item in output.formations}
    evidence = defaultdict(list)
    for item in output.evidence:
        evidence[item.subject_id].append(item)
    items = []
    for assessment in sorted(output.assessments, key=lambda item: (-(item.priority or 0), item.id)):
        item = formation[assessment.formation_id]
        items.append(
            {
                "subject": item.subject_account_id,
                "kind": item.kind,
                "transaction_ids": list(item.transaction_ids),
                "priority": assessment.priority,
                "band": assessment.band,
                "reasons": [asdict(reason) for reason in assessment.reason_codes],
                "evidence": [
                    {"kind": row.kind, "accounts": row.account_ids, "transactions": row.transaction_ids}
                    for row in evidence[item.id]
                ],
            }
        )
    return latency_ms, items


def metrics(truth, scores, flags, k):
    ordered = sorted(truth, key=lambda key: (-scores[key], key))
    tp = sum(truth[key] for key in flags)
    fp = len(flags) - tp
    positives = sum(truth.values())
    negatives = len(truth) - positives
    fn = positives - tp
    tn = negatives - fp

    def ratio(n, d):
        return n / d if d else None

    def wilson(n, d):
        if not d:
            return None
        p = n / d
        z = 1.959964
        delta = z * math.sqrt(p * (1 - p) / d + z * z / (4 * d * d))
        mid = p + z * z / (2 * d)
        return [max(0, (mid - delta) / (1 + z * z / d)), min(1, (mid + delta) / (1 + z * z / d))]

    by_score = defaultdict(Counter)
    for key in truth:
        by_score[scores[key]][truth[key]] += 1
    acc_pos = acc_neg = 0
    ap = auc_sum = 0.0
    for value in sorted(by_score, reverse=True):
        pos, neg = by_score[value][True], by_score[value][False]
        auc_sum += pos * (negatives - acc_neg - neg / 2)
        acc_pos += pos
        acc_neg += neg
        if positives:
            ap += pos / positives * acc_pos / (acc_pos + acc_neg)
    top = ordered[:k]
    return {
        "n": len(truth),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, positives),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "fpr": ratio(fp, negatives),
        "fnr": ratio(fn, positives),
        "pr_auc_average_precision": ap if positives else None,
        "roc_auc": ratio(auc_sum, positives * negatives),
        "k": len(top),
        "precision_at_k": ratio(sum(truth[key] for key in top), len(top)),
        "recall_at_k": ratio(sum(truth[key] for key in top), positives),
        "recall_naive_wilson_95": wilson(tp, positives),
        "fpr_naive_wilson_95": wilson(fp, negatives),
    }


def ground_truth(groups, transfers):
    positive_tx = {
        tx.transaction_id
        for tx in transfers
        if groups[tx.sender.split(":")[0]].fraud
        and not (groups[tx.sender.split(":")[0]].name == "mixed_fraud_network" and tx.sender.endswith(":l"))
    }
    positive_accounts = {
        account for tx in transfers if tx.transaction_id in positive_tx for account in (tx.sender, tx.receiver)
    }
    return {
        "network": {group: scenario.fraud for group, scenario in groups.items()},
        "account": {a: a in positive_accounts for tx in transfers for a in (tx.sender, tx.receiver)},
        "transaction": {tx.transaction_id: tx.transaction_id in positive_tx for tx in transfers},
    }


def graph_metrics(truth, items):
    scores = {unit: dict.fromkeys(labels, 0) for unit, labels in truth.items()}
    flags = {unit: set() for unit in truth}
    for item in items:
        keys = {
            "network": [item["subject"].split(":")[0]],
            "account": [item["subject"]],
            "transaction": item["transaction_ids"],
        }
        for unit, values in keys.items():
            for value in values:
                scores[unit][value] = max(scores[unit][value], item["priority"] or 0)
                if item["band"] in BANDS:
                    flags[unit].add(value)
    return {unit: metrics(labels, scores[unit], flags[unit], 10) for unit, labels in truth.items()}


def baseline_scores(transfers):
    largest = defaultdict(int)
    neighbors = defaultdict(set)
    for tx in transfers:
        group = tx.sender.split(":")[0]
        largest[group] = max(largest[group], tx.amount_minor)
        neighbors[tx.sender].add(tx.receiver)
        neighbors[tx.receiver].add(tx.sender)
    degree = defaultdict(int)
    for account, linked in neighbors.items():
        group = account.split(":")[0]
        degree[group] = max(degree[group], len(linked))
    return {"amount_50000_kzt": (largest, 5_000_000), "counterparties_5": (degree, 5)}


def evaluate(seed, prevalence):
    randomizer = random.Random(seed)
    count = 100
    positives = round(prevalence * count)
    fraud = [scenario for scenario in SCENARIOS if scenario.fraud]
    clean = [scenario for scenario in SCENARIOS if not scenario.fraud]
    specs = randomizer.choices(fraud, k=positives) + randomizer.choices(clean, k=count - positives)
    randomizer.shuffle(specs)
    groups = {f"g{i:03}": scenario for i, scenario in enumerate(specs)}
    transfers = [
        tx
        for group, scenario in groups.items()
        for tx in materialize(
            scenario, group, scale=randomizer.uniform(0.65, 1.45), offset=randomizer.randrange(21 * DAY)
        )
    ]
    randomizer.shuffle(transfers)
    latency, items = detect(transfers, f"audit-{seed}-{positives}")
    truth = ground_truth(groups, transfers)
    baseline = {}
    for name, (scores, cutoff) in baseline_scores(transfers).items():
        baseline[name] = metrics(
            truth["network"], scores, {key for key, score in scores.items() if score >= cutoff}, 10
        )
    return {
        "seed": seed,
        "prevalence": prevalence,
        "latency_ms": latency,
        "alert_count": sum(item["band"] in BANDS for item in items),
        "watch_count": sum(item["band"] == "insufficient_evidence" for item in items),
        "families": dict(Counter(scenario.name for scenario in specs)),
        "graph": graph_metrics(truth, items),
        "baselines_network": baseline,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    scenarios = []
    for index, scenario in enumerate(SCENARIOS):
        group = f"s{index:02}"
        transactions = list(materialize(scenario, group))
        latency, items = detect(transactions, group)
        truth = ground_truth({group: scenario}, transactions)
        scenarios.append(
            {
                "scenario": scenario.name,
                "limitation": scenario.limitation,
                "fraud": scenario.fraud,
                "expected": "alert" if scenario.fraud else "no_alert",
                "latency_ms": latency,
                "input": [asdict(tx) for tx in transactions],
                "truth": truth,
                "items": items,
                "result": graph_metrics(truth, items),
            }
        )
    runs = [evaluate(seed, prevalence) for prevalence in (0.01, 0.05, 0.20) for seed in (7101, 7193, 7283)]
    args.output.write_text(json.dumps({"scenarios": scenarios, "runs": runs}, indent=2, default=str) + "\n")
    for case in scenarios:
        result = case["result"]["network"]
        print(
            case["scenario"],
            case["expected"],
            "PASS" if not (result["fp"] or result["fn"]) else "FAIL",
            [(item["kind"], item["band"], item["priority"]) for item in case["items"]],
        )
    for prevalence in (0.01, 0.05, 0.20):
        results = [r for r in runs if r["prevalence"] == prevalence]
        print(prevalence, "median latency_ms", round(statistics.median(r["latency_ms"] for r in results), 2))
        for unit in ("network", "account", "transaction"):
            print(unit, "TP FP TN FN", [sum(r["graph"][unit][k] for r in results) for k in ("tp", "fp", "tn", "fn")])


if __name__ == "__main__":
    main()
