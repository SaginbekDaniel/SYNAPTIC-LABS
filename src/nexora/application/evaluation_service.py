"""Read-only access to recorded benchmark runs (``scripts/run_benchmark.py`` artifacts).

The API never computes or edits metrics: it projects the report a benchmark run wrote to disk
into a compact, typed shape for the Evaluation screen. If no run exists the caller gets a 404
with an actionable message — the UI must never invent numbers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nexora.application.errors import Invalid, NotFound

LABEL = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
#: Methods whose false-positive / false-negative examples are shown (detection engines only).
_K = ("10", "25", "50", "100")


def _index(results_dir: Path) -> dict[str, Any]:
    path = results_dir / "index.json"
    if not path.is_file():
        raise NotFound("BENCHMARK_NOT_RUN", "no benchmark run recorded; run scripts/run_benchmark.py")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def list_runs(results_dir: Path) -> dict[str, Any]:
    index = _index(results_dir)
    runs = [
        {
            "label": r["label"],
            "created_at": r["created_at"],
            "code_commit": r.get("code_commit"),
            "splits": r.get("splits", []),
        }
        for r in sorted(index.get("runs", []), key=lambda r: r["created_at"], reverse=True)
    ]
    return {"latest": index.get("latest"), "runs": runs}


def _load(results_dir: Path, label: str) -> dict[str, Any]:
    if not LABEL.match(label):
        raise Invalid("INVALID_RUN_LABEL", "run label may contain only letters, digits, '.', '_' and '-'")
    index = _index(results_dir)
    entry = next((r for r in index.get("runs", []) if r["label"] == label), None)
    if entry is None:
        raise NotFound("BENCHMARK_RUN_NOT_FOUND", f"benchmark run {label!r} is not recorded")
    path = (results_dir / entry["path"]).resolve()
    if results_dir.resolve() not in path.parents or not path.is_file():
        raise NotFound("BENCHMARK_RUN_NOT_FOUND", f"report for {label!r} is missing")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _scenario(m: dict[str, Any]) -> dict[str, Any]:
    s = m["unit_scenario"]
    return {k: s[k] for k in ("tp", "fp", "fn", "tn", "precision", "recall", "f1", "fpr", "fnr")} | {
        "ci95": {k: s["ci95"].get(k) for k in ("precision", "recall", "f1", "fpr")}
    }


def _summary(split: str, method: str, m: dict[str, Any]) -> dict[str, Any]:
    a, acc = m["unit_alert"], m["unit_account"]
    return {
        "split": split,
        "method": method,
        "scenario": _scenario(m),
        "alerts": {
            k: a[k]
            for k in (
                "raised",
                "precision",
                "alerts_per_network",
                "background_alerts_per_network",
                "alerts_per_1000_transactions",
                "on_benign_scenarios",
                "on_background",
                "duplicates_of_detected_scenario",
            )
        },
        "queue": [
            {"k": int(k), "precision": m["unit_queue"][k]["precision"], "recall": m["unit_queue"][k]["recall"]}
            for k in _K
            if k in m["unit_queue"]
        ],
        "accounts": {k: acc[k] for k in ("precision", "recall", "fpr")},
        "latency_ms": m["latency_ms"],
        "abstentions": m["abstentions"],
        "networks": m["networks"],
        "transactions": m["transactions"],
        "by_family": [
            {
                "family": fam,
                "label": f["label"],
                "networks": f["networks"],
                "rate": f["rate"],
                "rate_kind": f["rate_kind"],
                "alerts_per_network": f["alerts_per_network"],
            }
            for fam, f in sorted(m["by_family"].items())
        ],
    }


def _experiment(kind: str, e: dict[str, Any]) -> dict[str, Any]:
    m = e["metrics"]
    return {
        "kind": kind,
        "name": e["name"],
        "method": e.get("method", "B5_v2_full"),
        "description": e["description"],
        "split": e["split"],
        "scenario": _scenario(m),
        "alerts_per_network": m["unit_alert"]["alerts_per_network"],
        "precision_at_10": m["unit_queue"]["10"]["precision"],
        "changed": e.get("changed", 0),
        "transitions": e.get("transitions", {}),
        "band_changes": {k: v for k, v in (e.get("band_changes") or {}).items() if v and "->" in k},
    }


def get_run(results_dir: Path, label: str) -> dict[str, Any]:
    r = _load(results_dir, label)
    run, suite = r["run"], r["suite"]
    examples = [
        {
            "split": split,
            "method": method,
            "false_positive_count": ex["false_positive_count"],
            "false_negative_count": ex["false_negative_count"],
            "false_positives": ex["false_positives"],
            "false_negatives": ex["false_negatives"],
            "false_positives_by_family": ex.get("false_positives_by_family", {}),
            "false_negatives_by_family": ex.get("false_negatives_by_family", {}),
        }
        for split, per in r.get("examples", {}).items()
        for method, ex in per.items()
    ]
    return {
        "label": run["label"],
        "disclaimer": r["disclaimer"],
        "run": {
            k: run.get(k)
            for k in (
                "created_at",
                "duration_s",
                "code_commit",
                "code_dirty",
                "python",
                "networkx",
                "cpu",
                "cpu_count",
                "splits_evaluated",
            )
        },
        "suite": {
            "benchmark_version": suite["benchmark_version"],
            "master_seed": suite["master_seed"],
            "networks_per_family": suite["networks_per_family"],
            "families": suite["families"],
            "splits": [{"split": name, **{k: v for k, v in s.items()}} for name, s in suite["splits"].items()],
        },
        "evaluation_units": r["evaluation_units"],
        "matching_rule": r["matching_rule"]["text"],
        "operating_points": r["operating_points"],
        "methods": [
            {
                "name": m["name"],
                "group": m["group"],
                "description": m["description"],
                "config_sha256": m.get("config_sha256"),
                "threshold": m.get("threshold_fitted_on_dev"),
            }
            for m in r["methods"]
        ],
        "results": [_summary(split, name, m) for split, per in r["results"].items() for name, m in per.items()],
        "time_to_detection": [
            {
                "split": split,
                "method": name,
                **{k: t[k] for k in ("median_days", "max_days", "detected_networks", "undetected_networks")},
                "transient_detections": t.get("transient_detections", 0),
            }
            for split, per in r.get("time_to_detection", {}).items()
            for name, t in per.items()
        ],
        "examples": examples,
        "experiments": [_experiment("ablation", e) for e in r.get("ablations", [])]
        + [_experiment("robustness", e) for e in r.get("robustness", [])],
        "scale": r.get("scale", []),
    }
