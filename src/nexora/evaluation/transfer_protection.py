"""Reproducible transfer-intent evaluation on the offline synthetic holdout."""

from __future__ import annotations

import json
import math
import random
import subprocess
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from pydantic import BaseModel, Field

from nexora.analytics.config import default_config
from nexora.analytics.risk import opens_alert
from nexora.application.transfer_demo import load_policy
from nexora.application.transfer_protection import (
    ContextFact,
    ContextKind,
    Decision,
    Failure,
    RecipientProfile,
    TimedTransfer,
    TransferIntent,
    assess,
)
from nexora.application.transfer_snapshot import prepare_profile
from nexora.domain.ids import sha256_hex, transaction_uuid
from nexora.domain.transfers import ObservedTransfer

ROOT = Path(__file__).resolve().parents[3]
HOLDOUT = ROOT / "benchmarks" / "transfer_protection" / "holdout-v1.json"
CUTOFF = datetime(2026, 8, 1, tzinfo=UTC)
INTERVENTIONS = frozenset({"WARN", "STEP_UP"})
EXPLANATIONS: dict[str, ContextKind] = {
    "family": "FAMILY_TRANSFER",
    "payroll": "PAYROLL",
    "settlement": "MERCHANT_SETTLEMENT",
    "refund": "REFUND",
}


class Group(BaseModel):
    recipe: str
    fraud: bool
    count: int = Field(gt=0)


class Holdout(BaseModel):
    version: str
    seed: int
    amount_baseline_minor: int
    groups: list[Group]


@dataclass(frozen=True)
class Sample:
    intent: TransferIntent
    profile: RecipientProfile | None
    is_first_transfer: bool
    failure: Failure | None = None


def _generate_sample(recipe: str, index: int, rng: random.Random) -> Sample:
    config = default_config()
    case = f"holdout-{index:04}"
    sender, recipient = f"{case}-sender", f"{case}-recipient"
    amount = rng.randrange(1_000_000, 34_000_000)
    if recipe == "large_invoice":
        amount = rng.randrange(30_000_000, 110_000_000)
    intent = TransferIntent(case, sender, recipient, CUTOFF, amount)
    history: list[TimedTransfer] = []

    def add(src: str, dst: str, value: int, days: int, *, day_precision: bool = False) -> None:
        when = CUTOFF - timedelta(days=days)
        ref = f"entry-{len(history) + 1}"
        history.append(
            TimedTransfer(
                observed=ObservedTransfer(
                    transaction_id=transaction_uuid(case, "holdout", ref),
                    source_transaction_id=ref,
                    sender=src,
                    receiver=dst,
                    amount_minor=value,
                    currency="KZT",
                    observed_date=when.date(),
                    occurred_at=None if day_precision else when,
                    precision="day" if day_precision else "timestamp",
                ),
                known_at=when + timedelta(hours=2),
            )
        )

    repeat = recipe in {"regular", "family", "large_invoice", "slow_collection", "report_only", "stale"}
    failure: Failure | None = None
    if recipe == "timeout":
        failure = "TIMEOUT"
    if recipe == "dependency_failure":
        failure = "DEPENDENCY_FAILURE"
    if failure or recipe == "missing":
        return Sample(intent, None, False, failure)

    context: list[ContextFact] = []
    unit = rng.randrange(2_000_000, 6_000_000)
    if recipe == "chain":
        intermediaries = [f"{case}-hop-{j}" for j in range(3)]
        route = [*intermediaries, recipient]
        for j, (src, dst) in enumerate(pairwise(route)):
            add(src, dst, unit - j * 50_000, 4 - j)
    elif recipe in {"payroll", "refund"}:
        n = rng.randrange(5, 9)
        add(f"{case}-treasury", recipient, unit * n, 5)
        for i in range(n):
            add(recipient, f"{case}-payee-{i}", unit, 3)
            add(f"{case}-payee-{i}", f"{case}-external-{i}", unit, 2)
    elif recipe in {
        "family",
        "settlement",
        "timed_collection",
        "timed_with_report",
        "unexplained_collection",
        "partial",
        "stale",
        "slow_collection",
        "ambiguous_collection",
    }:
        n = rng.randrange(3, 7)
        ambiguous = recipe == "ambiguous_collection"
        for j in range(n):
            payer = sender if repeat and j == 0 else f"{case}-payer-{j}"
            add(payer, recipient, unit, 12 if recipe == "slow_collection" else 3, day_precision=ambiguous)
        add(recipient, f"{case}-beneficiary", unit * n, 3 if ambiguous else 2, day_precision=ambiguous)
        if ambiguous:
            add(f"{case}-extra", recipient, 200, 9, day_precision=True)
    else:
        for d in (32, 18, 7):
            add(sender if repeat else f"{case}-vendor", recipient, unit, d)

    if repeat:
        add(sender, recipient, 500_000, 19)
        add(sender, recipient, 500_000, 10)
    metadata_time = CUTOFF - timedelta(days=1)
    if recipe in EXPLANATIONS:
        context.append(
            ContextFact(
                source_ref=f"{case}-settlement-register",
                kind=EXPLANATIONS[recipe],
                recipient=recipient,
                occurred_at=metadata_time,
                known_at=metadata_time,
                transaction_ids=tuple(row.observed.transaction_id for row in history),
            )
        )
    if recipe in {"timed_with_report", "report_only"}:
        context.append(
            ContextFact(
                source_ref=f"{case}-independent-incident-register",
                kind="CONFIRMED_REPORT",
                recipient=recipient,
                occurred_at=metadata_time,
                known_at=metadata_time,
            )
        )

    profile_as_of = CUTOFF - timedelta(hours=12) if recipe == "stale" else CUTOFF
    snapshot_intent = TransferIntent(case, sender, recipient, profile_as_of, amount)
    profile = prepare_profile(
        snapshot_intent,
        tuple(history),
        tuple(context),
        config,
        scope="partial" if recipe == "partial" else "complete",
        valid_until=CUTOFF - timedelta(hours=1) if recipe == "stale" else None,
    )
    prior = any(
        row.observed.sender == sender and row.observed.receiver == recipient and row.available(CUTOFF)
        for row in history
    )
    return Sample(intent, profile, not prior)


def _samples(holdout: Holdout) -> Iterator[tuple[Sample, bool, str]]:
    rng = random.Random(holdout.seed)
    index = 0
    for group in holdout.groups:
        for _ in range(group.count):
            index += 1
            yield _generate_sample(group.recipe, index, rng), group.fraud, group.recipe


def _rates(entries: list[tuple[bool, Decision, int]]) -> dict[str, Any]:
    outcomes = Counter(decision for _, decision, _ in entries)
    tp = sum(label and decision in INTERVENTIONS for label, decision, _ in entries)
    fp = sum(not label and decision in INTERVENTIONS for label, decision, _ in entries)
    fn = sum(label and decision not in INTERVENTIONS for label, decision, _ in entries)
    tn = len(entries) - tp - fp - fn

    def proportion(a: int, b: int) -> float | None:
        return a / b if b else None

    latency = sorted(ns for _, _, ns in entries)
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": proportion(tp, tp + fp),
        "recall": proportion(tp, tp + fn),
        "false_positive_rate": proportion(fp, fp + tn),
        "false_warnings_per_1000_legitimate": proportion(fp * 1000, fp + tn),
        "limited_signal_rate": proportion(outcomes["LIMITED_SIGNAL"], len(entries)),
        "unavailable_rate": proportion(outcomes["UNAVAILABLE"], len(entries)),
        "decisions": dict(sorted(outcomes.items())),
        "latency_ms": {
            f"p{p}": latency[math.ceil(len(latency) * p / 100) - 1] / 1_000_000 if latency else None
            for p in (50, 95, 99)
        },
    }


def evaluate(path: Path = HOLDOUT) -> dict[str, Any]:
    raw = path.read_bytes()
    holdout = Holdout.model_validate_json(raw)
    config, policy = default_config(), load_policy()

    def by_amount(sample: Sample) -> Decision:
        return "WARN" if sample.intent.amount_minor >= holdout.amount_baseline_minor else "ALLOW"

    def by_relationship(sample: Sample) -> Decision:
        return "WARN" if sample.is_first_transfer else "ALLOW"

    def graph_only(sample: Sample) -> Decision:
        if sample.failure:
            return "UNAVAILABLE"
        if sample.profile is None:
            return "LIMITED_SIGNAL"
        bands = [f.band for f in sample.profile.formations]
        if any(b != "insufficient_evidence" and opens_alert(b, config.risk_policy) for b in bands):
            return "WARN"
        if "insufficient_evidence" in bands:
            return "LIMITED_SIGNAL"
        return "ALLOW"

    def full_policy(sample: Sample) -> Decision:
        return assess(sample.intent, sample.profile, policy, failure=sample.failure).decision

    methods: dict[str, Callable[[Sample], Decision]] = {
        "amount_only": by_amount,
        "first_time_recipient": by_relationship,
        "graph_only": graph_only,
        "transfer_protection": full_policy,
    }
    results: dict[str, list[tuple[bool, Decision, int]]] = {method: [] for method in methods}
    strata: dict[str, Counter[str]] = {}
    snapshot_manifest: list[tuple[str, str | None]] = []
    for sample, label, recipe in _samples(holdout):
        snapshot_manifest.append((sample.intent.scenario_id, sample.profile.snapshot_id if sample.profile else None))
        for name, run in methods.items():
            start = perf_counter_ns()
            decision = run(sample)
            elapsed = perf_counter_ns() - start
            results[name].append((label, decision, elapsed))
            if name == "transfer_protection":
                strata.setdefault(f"{recipe}:{'fraud' if label else 'legitimate'}", Counter())[decision] += 1

    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        git_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        git_commit, git_dirty = None, None
    full = results["transfer_protection"]
    return {
        "dataset_version": holdout.version,
        "dataset_sha256": sha256_hex(raw),
        "snapshot_manifest_sha256": sha256_hex(json.dumps(snapshot_manifest)),
        "git_commit": git_commit,
        "git_worktree_dirty": git_dirty,
        "policy_version": policy.version,
        "analysis_config_sha256": config.config_sha256,
        "graph_policy_version": config.policy_version,
        "scenario_count": len(full),
        "legitimate_count": sum(not label for label, _, _ in full),
        "fraud_count": sum(label for label, _, _ in full),
        "amount_baseline_minor": str(holdout.amount_baseline_minor),
        "graph_only_alert_min_band": config.risk_policy["alert_min_band"],
        "latency_scope": "in-process decision on prepared inputs; excludes graph preparation, HTTP and queueing",
        "results": {name: _rates(entries) for name, entries in results.items()},
        "policy_decisions_by_stratum": {name: dict(sorted(counts.items())) for name, counts in sorted(strata.items())},
        "limitations": [
            "One synthetic holdout with recurring generator recipes; effective sample size is lower than row count.",
            "Corroboration, business context, missing coverage and outages are synthetic observations.",
            "Metrics include abstentions as no intervention. They do not estimate real banking performance.",
        ],
    }
