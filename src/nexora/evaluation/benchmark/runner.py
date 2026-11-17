"""Benchmark orchestration and reproducible report artifacts.

Labels are read only by: (a) baseline threshold fitting on the development split and
(b) scoring after a method has produced its predictions. Methods never receive a
``TruthRecord``.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import platform
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import networkx

from nexora.evaluation.benchmark.methods import Method, NexoraMethod
from nexora.evaluation.benchmark.metrics import (
    MATCH_MIN_ACCOUNT_SHARE,
    NetworkOutcome,
    matches,
    outcome_dict,
    score_network,
    summarise,
)
from nexora.evaluation.benchmark.suite import Network, NetworkInput, Suite

REPORT_SCHEMA = "nexora-benchmark-report/1"
DISCLAIMER = (
    "SYNTHETIC BENCHMARK. All networks, labels and metrics come from the NEXORA synthetic scenario "
    "generator, not from bank data. Results describe behaviour on this synthetic distribution only "
    "and are not estimates of real-world fraud detection accuracy."
)
UNITS = {
    "unit_scenario": "One planted scenario per network. TP = a raised alert matches a planted suspicious "
    "scenario; FP = a raised alert matches a planted benign scenario.",
    "unit_alert": "Every raised alert. True only if it matches a planted suspicious scenario; alerts on "
    "benign scenarios or unlabelled background are false.",
    "unit_queue": "Raised alerts of a split pooled and sorted by review score. Precision@K/Recall@K count "
    "distinct suspicious scenarios; duplicate alerts on one scenario waste a slot.",
    "unit_account": "Accounts in raised alerts vs accounts of planted suspicious scenarios. Over-counts "
    "large networks; reported separately and never combined with scenario metrics.",
}


@dataclass
class MethodRun:
    outcomes: list[NetworkOutcome]
    ranked: list[tuple[float, str, Any, Any]]


def run_method(method: Method, networks: Sequence[Network]) -> MethodRun:
    outcomes: list[NetworkOutcome] = []
    ranked: list[tuple[float, str, Any, Any]] = []
    for net in networks:
        result = method.run(net.input)
        accounts = {r["sender_account_id"] for r in net.input.rows} | {r["receiver_account_id"] for r in net.input.rows}
        outcomes.append(score_network(net.split, net.truth, result, accounts))
        for p in result.predictions:
            if p.status == "raised" and p.score is not None:
                ranked.append((p.score, net.truth.network_id, p, net.truth))
    return MethodRun(outcomes, ranked)


def truncated(inp: NetworkInput, last_day: date) -> NetworkInput:
    rows = tuple(r for r in inp.rows if date.fromisoformat(r["observed_date"]) <= last_day)
    return NetworkInput(inp.network_id, rows, inp.coverage_contract, (inp.window[0], last_day))


def time_to_detection(method: Method, networks: Sequence[Network]) -> dict[str, Any]:
    """Replay each positive network day by day (simulated event time).

    TTD = first replay day on which a raised alert matches the scenario minus the day of the
    scenario's first transaction. Only networks detected on the full window get a TTD; networks
    that raise a matching alert mid-replay but not on the full window are counted as *transient*
    (the alert would have been shown and later disappeared).
    """
    per_family: dict[str, list[int]] = {}
    undetected = transient = 0
    for net in networks:
        if net.truth.label != "suspicious":
            continue
        scenario = set(net.truth.transaction_ids)
        days = sorted(
            {date.fromisoformat(r["observed_date"]) for r in net.input.rows if r["source_transaction_id"] in scenario}
        )
        if not days:
            continue
        detected_full = any(p.status == "raised" and matches(p, net.truth) for p in method.run(net.input).predictions)
        found: int | None = None
        day = days[0]
        while day <= net.input.window[1]:
            result = method.run(truncated(net.input, day))
            if any(p.status == "raised" and matches(p, net.truth) for p in result.predictions):
                found = (day - days[0]).days
                break
            day += dt.timedelta(days=1)
        if not detected_full:
            undetected += 1
            transient += found is not None
            continue
        assert found is not None
        per_family.setdefault(net.truth.family, []).append(found)
    all_values = sorted(v for vs in per_family.values() for v in vs)
    return {
        "unit": "days of simulated event time from the scenario's first transfer to the first matching alert",
        "detected_networks": len(all_values),
        "undetected_networks": undetected,
        "transient_detections": transient,
        "median_days": all_values[len(all_values) // 2] if all_values else None,
        "max_days": all_values[-1] if all_values else None,
        "by_family": {f: {"median_days": sorted(v)[len(v) // 2], "n": len(v)} for f, v in sorted(per_family.items())},
    }


def provenance() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    status = git("status", "--porcelain")
    cpu = platform.processor() or platform.machine()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "code_commit": git("rev-parse", "HEAD"),
        "code_dirty": bool(status) if status is not None else None,
        "python": platform.python_version(),
        "networkx": networkx.__version__,
        "platform": platform.platform(),
        "cpu": cpu,
        "cpu_count": os.cpu_count(),
    }


def evaluate(
    suite: Suite,
    methods: Sequence[Method],
    *,
    splits: Sequence[str],
    label: str,
    ttd_methods: Sequence[str] = (),
    example_methods: Sequence[str] = (),
    extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = time.perf_counter()
    dev = suite.split("dev")
    for m in methods:
        m.fit(dev)
    results: dict[str, dict[str, Any]] = {}
    examples: dict[str, dict[str, Any]] = {}
    ttd: dict[str, dict[str, Any]] = {}
    raw: list[dict[str, Any]] = []
    for split in splits:
        nets = suite.split(split)
        results[split] = {}
        for m in methods:
            run = run_method(m, nets)
            results[split][m.name] = summarise(run.outcomes, run.ranked)
            raw.extend({"method": m.name, **outcome_dict(o)} for o in run.outcomes)
            if m.name in example_methods:
                examples.setdefault(split, {})[m.name] = _examples(run.outcomes)
            if m.name in ttd_methods and isinstance(m, NexoraMethod):
                ttd.setdefault(split, {})[m.name] = time_to_detection(m, nets)
    report = {
        "schema": REPORT_SCHEMA,
        "disclaimer": DISCLAIMER,
        "run": {
            "label": label,
            "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "duration_s": round(time.perf_counter() - started, 1),
            "splits_evaluated": list(splits),
            **provenance(),
        },
        "suite": suite.manifest(),
        "evaluation_units": UNITS,
        "matching_rule": {
            "min_account_share": MATCH_MIN_ACCOUNT_SHARE,
            "requires_shared_transaction": True,
            "text": "A prediction matches a scenario when >= 50% of its accounts belong to the scenario and, "
            "if it cites transactions, at least one is a planted scenario transaction.",
        },
        "operating_points": {
            "nexora": "raised = band >= policy alert_min_band (medium); insufficient_evidence counts as abstention",
            "baselines": "raised = account score >= threshold fitted on the development split (max scenario F1)",
        },
        "methods": [m.describe() for m in methods],
        "results": results,
        "time_to_detection": ttd,
        "examples": examples,
        **(extra or {}),
    }
    return report, raw


def _examples(outcomes: Sequence[NetworkOutcome], limit: int = 12) -> dict[str, Any]:
    def row(o: NetworkOutcome) -> dict[str, Any]:
        return {
            "network_id": o.network_id,
            "family": o.family,
            "variant": o.variant,
            "difficulty": o.difficulty,
            "expected": o.expected,
            "reason": o.reason,
            "alerts": o.scenario_alerts,
        }

    fps = [o for o in outcomes if o.outcome == "FP"]
    fns = [o for o in outcomes if o.outcome == "FN"]
    return {
        "false_positives": [row(o) for o in sorted(fps, key=lambda o: (o.family, o.network_id))[:limit]],
        "false_negatives": [row(o) for o in sorted(fns, key=lambda o: (o.family, o.network_id))[:limit]],
        "false_positive_count": len(fps),
        "false_negative_count": len(fns),
    }


def write_report(report: dict[str, Any], raw: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    # mtime=0 keeps the archive byte-identical across reruns with identical outcomes.
    payload = "".join(json.dumps(r, sort_keys=True) + "\n" for r in raw).encode("utf-8")
    (out_dir / "outcomes.jsonl.gz").write_bytes(gzip.compress(payload, mtime=0))
    from nexora.evaluation.benchmark.report import render_markdown

    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
