"""Run the locked evaluation protocol (docs/evaluation/EXPERIMENT_PROTOCOL.md).

    uv run python scripts/run_sealed_evaluation.py --split sealed
    uv run python scripts/run_sealed_evaluation.py --split dev --out /tmp/dev.json   # development only

Compares the candidate (current configuration) with the exact baseline merged at 4c01a7a
(``v2_shipped``), runs ablations and simple baselines, computes paired bootstrap intervals
over datasets and applies the pre-registered decision rule mechanically. The sealed split
is meant to be run once; the artifact records the code commit and every hash it used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexora.analytics.config import default_config  # noqa: E402
from nexora.evaluation import benchmark as b  # noqa: E402
from nexora.evaluation import entity_metrics as em  # noqa: E402

BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261117
MAX_RECALL_DROP = 0.02


def _no_hypothesis_gate(det: dict[str, Any], pol: dict[str, Any]) -> None:
    pol.pop("hypothesis", None)


def _no_hypotheses(det: dict[str, Any], pol: dict[str, Any]) -> None:
    det.pop("hypotheses", None)
    pol.pop("hypothesis", None)


def experiments(cfg: Any) -> list[b.Experiment]:
    v = b.config_variant
    return [
        b.Experiment("candidate", b.nexora_method(cfg)),
        b.Experiment("baseline_v2", b.nexora_method(v(cfg, b.VARIANTS["v2_shipped"]))),
        b.Experiment("ablation_engine_without_gate", b.nexora_method(v(cfg, _no_hypothesis_gate))),
        b.Experiment("ablation_without_hypotheses", b.nexora_method(v(cfg, _no_hypotheses))),
        b.Experiment("ablation_minus_peer", b.nexora_method(v(cfg, b.VARIANTS["minus_peer"]))),
        b.Experiment("ablation_minus_temporal", b.nexora_method(v(cfg, b.VARIANTS["minus_temporal"]))),
        b.Experiment("ablation_minus_abstention", b.nexora_method(v(cfg, b.VARIANTS["minus_coverage_abstention"]))),
        b.Experiment("v1_shipped", b.nexora_method(v(cfg, b.VARIANTS["v1_shipped"]))),
        b.Experiment("B3_structure_only", b.structure_only_method(cfg)),
        b.Experiment("B1_rules", b.rules_method),
        b.Experiment("B0_volume", b.volume_method, budget_from="candidate"),
    ]  # fmt: skip


def _scen(evals: list[b.DatasetEval], key: str) -> float | None:
    v = b.summarize(evals)["scenario"][key]
    return None if v is None else float(v)


def _dp5(evals: list[b.DatasetEval]) -> float | None:
    v = b.summarize(evals)["queue"]["distinct_p_at_5"]
    return None if v is None else float(v)


def paired_bootstrap(a: list[b.DatasetEval], c: list[b.DatasetEval], metric: Any) -> dict[str, Any]:
    """95% percentile interval of metric(candidate) - metric(baseline), datasets resampled jointly."""
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(a)
    diffs: list[float] = []
    for _ in range(BOOTSTRAP_DRAWS):
        idx = [rng.randrange(n) for _ in range(n)]
        ma, mc = metric([a[i] for i in idx]), metric([c[i] for i in idx])
        if ma is not None and mc is not None:
            diffs.append(mc - ma)
    diffs.sort()
    point_a, point_c = metric(a), metric(c)
    return {
        "baseline": point_a,
        "candidate": point_c,
        "difference": None if point_a is None or point_c is None else round(point_c - point_a, 4),
        "ci95": [round(diffs[int(0.025 * len(diffs))], 4), round(diffs[int(0.975 * len(diffs)) - 1], 4)],
        "draws": len(diffs),
    }


def decide(base: dict[str, Any], cand: dict[str, Any], boot: dict[str, Any]) -> dict[str, Any]:
    rb, rc = base["scenario"]["recall"], cand["scenario"]["recall"]
    hb, hc = base["scenario"]["high_band_fpr"], cand["scenario"]["high_band_fpr"]
    checks = {
        "recall_drop_at_most_2pp": rc >= rb - MAX_RECALL_DROP,
        "high_band_fpr_not_increased": hc <= hb,
        "fpr_improved_ci_excludes_zero": boot["fpr"]["difference"] < 0 and boot["fpr"]["ci95"][1] < 0,
        "distinct_p5_improved_ci_excludes_zero": boot["distinct_p_at_5"]["difference"] > 0
        and boot["distinct_p_at_5"]["ci95"][0] > 0,
    }
    improved = (
        checks["recall_drop_at_most_2pp"]
        and checks["high_band_fpr_not_increased"]
        and (checks["fpr_improved_ci_excludes_zero"] or checks["distinct_p5_improved_ci_excludes_zero"])
    )
    return {"checks": checks, "outcome": "improvement" if improved else "not_demonstrated"}


def git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()

    # Porcelain lines are "XY path"; X may be a space, so the output must not be stripped first.
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout
    return {"commit": run("rev-parse", "HEAD"), "dirty_paths": [ln for ln in porcelain.splitlines() if ln][:20]}


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def run(split: str) -> dict[str, Any]:
    cfg = default_config()
    started = time.perf_counter()
    datasets = b.load_split(split)
    res = b.run_experiments(datasets, experiments(cfg))
    summaries = {name: b.summarize(evals) for name, evals in res.items()}
    # Entity-level, ranking and band-reliability metrics (B-041) for every method; not part of the decision rule.
    entity = {name: em.entity_summary(evals) for name, evals in res.items()}
    boot = {
        "fpr": paired_bootstrap(res["baseline_v2"], res["candidate"], lambda e: _scen(e, "fpr")),
        "recall": paired_bootstrap(res["baseline_v2"], res["candidate"], lambda e: _scen(e, "recall")),
        "high_band_fpr": paired_bootstrap(res["baseline_v2"], res["candidate"], lambda e: _scen(e, "high_band_fpr")),
        "distinct_p_at_5": paired_bootstrap(res["baseline_v2"], res["candidate"], _dp5),
    }
    return {
        "schema_version": 1,
        "protocol": "docs/evaluation/EXPERIMENT_PROTOCOL.md",
        "split": split,
        "seeds": [b.SPLITS[split][0], b.SPLITS[split][-1]],
        "datasets": len(datasets),
        "split_sha256": b.split_hash(datasets),
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "synthetic": True,
        "code": git_state(),
        "hashes": {
            "sealed_generator": sha("src/nexora/evaluation/sealed_generator.py"),
            "harness": sha("src/nexora/evaluation/benchmark.py"),
            "candidate_config_sha256": cfg.config_sha256,
            "baseline_config_sha256": b.config_variant(cfg, b.VARIANTS["v2_shipped"]).config_sha256,
        },
        "environment": {"python": platform.python_version()},
        "results": {name: {**summary, "entity": entity[name]} for name, summary in summaries.items()},
        "bootstrap": {"draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, **boot},
        "decision": decide(summaries["baseline_v2"], summaries["candidate"], boot),
        "examples": b.examples(res["candidate"], limit=40),
        "runtime_seconds": round(time.perf_counter() - started, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="sealed", choices=sorted(b.SPLITS))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    out = Path(args.out or ROOT / "benchmarks" / "results" / f"{args.split}-evaluation.json")
    artifact = run(args.split)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    d = artifact["decision"]
    print(f"wrote {out} in {artifact['runtime_seconds']} s — decision: {d['outcome']} {d['checks']}")


if __name__ == "__main__":
    main()
