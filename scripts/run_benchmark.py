"""Run the NEXORA synthetic benchmark and write the evaluation artifact + report.

    uv run python scripts/run_benchmark.py

Outputs (both committed, so every quoted number is traceable to a run):

* ``benchmarks/results/bench-v1.json`` — the artifact served by ``GET /api/v1/evaluation``
* ``docs/EVALUATION.md`` — a human-readable rendering of the same artifact

Protocol: design decisions were made on ``dev``; ``validation`` was used only to confirm
them; ``holdout`` seeds were first evaluated by this script after the configuration was
frozen. All data is synthetic — the numbers say nothing about accuracy on real bank data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import subprocess
import sys
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexora.analytics.config import default_config  # noqa: E402
from nexora.evaluation import benchmark as b  # noqa: E402
from nexora.evaluation.generator import BENCH_GENERATOR_VERSION  # noqa: E402

OUTPUTS = ("benchmarks/results/bench-v1.json", "docs/EVALUATION.md")

METHODS: list[tuple[str, str, str]] = [
    (
        "nexora_v2",
        "NEXORA v2",
        "Full system: four structural detectors, temporal flow, peer statistics, risk-policy-v2.",
    ),
    (
        "nexora_v1",
        "NEXORA v1",
        "Configuration shipped before this benchmark: funnel + chain, temporal, risk-policy-v1.",
    ),
    ("B4_structure_temporal", "B4 Structure + temporal", "NEXORA v2 without the peer-statistics family."),
    ("B3_structure_only", "B3 Structure only", "Every structural formation alerts, ranked by structural strength."),
    ("B1_rules", "B1 Monitoring rules", "Per-account fan-in/out velocity, large amount and pass-through rules."),
    ("B0_volume", "B0 Turnover ranking", "Accounts ranked by turnover; flags the same number of items as NEXORA v2."),
    ("B2_pagerank", "B2 PageRank", "Amount-weighted PageRank; flags the same number of items as NEXORA v2."),
]
ABLATIONS = [k for k in b.VARIANTS if k not in ("v1_shipped", "v2_shipped")]


def git_state() -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()

    def is_output(path: str) -> bool:  # porcelain may report an untracked output directory
        return any(out == path or out.startswith(path.rstrip("/") + "/") for out in OUTPUTS)

    # Porcelain lines are "XY path"; X may be a space, so the output must not be stripped first.
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout
    dirty = [line[3:] for line in porcelain.splitlines() if line and not is_output(line[3:])]
    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(dirty), "dirty_paths": dirty[:20]}


def experiments(cfg: Any) -> list[b.Experiment]:
    return [
        b.Experiment("nexora_v2", b.nexora_method(cfg)),
        b.Experiment("nexora_v1", b.nexora_method(b.config_variant(cfg, b.VARIANTS["v1_shipped"]))),
        b.Experiment("B4_structure_temporal", b.nexora_method(b.config_variant(cfg, b.VARIANTS["minus_peer"]))),
        b.Experiment("B3_structure_only", b.structure_only_method(cfg)),
        b.Experiment("B1_rules", b.rules_method),
        b.Experiment("B0_volume", b.volume_method, budget_from="nexora_v2"),
        b.Experiment("B2_pagerank", b.pagerank_method, budget_from="nexora_v2"),
    ]


def run(splits: list[str]) -> dict[str, Any]:
    # bench-v1 is the historical v2 benchmark: pinned to the exact configuration merged at 4c01a7a so the
    # committed artifact stays reproducible and "NEXORA v2" means v2. v3 is evaluated by
    # scripts/run_sealed_evaluation.py against this same baseline.
    cfg = b.config_variant(default_config(), b.VARIANTS["v2_shipped"])
    started = time.perf_counter()
    loaded = {s: b.load_split(s) for s in splits}
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_version": b.BENCHMARK_VERSION,
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "synthetic": True,
        "code": git_state(),
        "environment": {"python": platform.python_version(), "platform": platform.platform(terse=True)},
        "generator": {"suite": b.SUITE, "version": BENCH_GENERATOR_VERSION},
        "config": {
            "detectors_version": str(cfg.detectors["version"]),
            "policy_version": cfg.policy_version,
            "config_sha256": cfg.config_sha256,
        },
        "protocol": {
            "matching_rule": (
                "An item matches the planted scenario containing its subject account with the largest account "
                "overlap, requiring at least min(2, item accounts) shared accounts."
            ),
            "flagged": "NEXORA alert with band medium, high or critical; insufficient_evidence alerts are 'surfaced'.",
            "units": {
                "scenario": "Planted network. Precision, recall, F1, FPR, FNR count scenarios only.",
                "alert": "Review item. Alert precision = flagged items that match a suspicious scenario.",
                "queue": "Per-dataset analyst queue in review order; P@K and Recall@K averaged over datasets.",
            },
            "splits": {
                "dev": "design decisions and error analysis",
                "validation": "confirmation only, no tuning",
                "holdout": "first evaluated after the configuration was frozen",
            },
        },
        "splits": {
            s: {
                "seeds": [b.SPLITS[s][0], b.SPLITS[s][-1]],
                "datasets": len(ds),
                "split_sha256": b.split_hash(ds),
                "precision_mix": {p: sum(1 for d in ds if d.precision == p) for p in sorted({d.precision for d in ds})},
                "manifest": b.dataset_manifest(ds),
            }
            for s, ds in loaded.items()
        },
        "methods": [{"id": i, "label": label, "description": d} for i, label, d in METHODS],
        "results": {},
        "ablations": {},
    }
    for split, ds in loaded.items():
        print(f"[{split}] methods", flush=True)
        res = b.run_experiments(ds, experiments(cfg))
        artifact["results"][split] = {name: b.summarize(evals) for name, evals in res.items()}
        if split in ("validation", "holdout"):
            print(f"[{split}] ablations", flush=True)
            abl = b.run_experiments(
                ds, [b.Experiment(v, b.nexora_method(b.config_variant(cfg, b.VARIANTS[v]))) for v in ABLATIONS]
            )
            artifact["ablations"][split] = {
                "full": artifact["results"][split]["nexora_v2"],
                **{name: b.summarize(evals) for name, evals in abl.items()},
            }
        if split == "holdout":
            artifact["examples"] = {"split": split, **b.examples(res["nexora_v2"], limit=12)}

    if "validation" in loaded:
        ds = loaded["validation"]
        full = [b.Experiment("full", b.nexora_method(cfg))]
        base = b.run_experiments(ds, full)["full"]
        rob: list[dict[str, Any]] = []
        for pid, (transform, desc) in b.PERTURBATIONS.items():
            print(f"[robustness] {pid}", flush=True)
            pert = b.run_experiments(ds, full, transform=transform)["full"]
            rob.append(
                {
                    "id": pid,
                    "description": desc,
                    "identical_to_base": b.identical_items(base, pert),
                    "summary": b.summarize(pert),
                }
            )
        sens: list[dict[str, Any]] = []
        for sid, edit in b.SENSITIVITY.items():
            print(f"[sensitivity] {sid}", flush=True)
            evals = b.run_experiments(ds, [b.Experiment(sid, b.nexora_method(b.config_variant(cfg, edit)))])[sid]
            sens.append({"id": sid, "summary": b.summarize(evals)})
        artifact["robustness"] = {"split": "validation", "base": b.summarize(base), "perturbations": rob}
        artifact["sensitivity"] = {"split": "validation", "variants": sens}
    artifact["runtime_seconds"] = round(time.perf_counter() - started, 1)
    artifact["limitations"] = [
        "All datasets are synthetic and generated by the same team that wrote the detectors; typologies, "
        "parameter ranges and hard negatives reflect our assumptions, not observed bank data.",
        "Scenario counts per split are small (tens per family); differences of one or two scenarios are noise.",
        "Priority is a triage ranking, not a calibrated probability of fraud.",
        "Latency is wall-clock time of the pure analysis pipeline on one CPU core of the benchmark machine; "
        "it excludes database I/O and is not a banking-scale throughput claim.",
        "Legitimate hubs capped by peer counter-evidence remain alerted at medium by design; any-alert FPR "
        "therefore stays high while high-band FPR measures the prioritisation effect.",
    ]
    return artifact


# ---------------------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------------------
def _f(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _r(num: int | None, den: int | None, stored: Any) -> str:
    """A count-backed ratio at 3 decimals, rounded once from its counts (half up, as on the Evaluation screen).

    Re-rounding the artifact's 4-decimal value can give a wrong digit (H-08); artifacts written before the
    numerators were emitted fall back to the stored ratio.
    """
    if num is None or not den:
        return _f(stored)
    return str((Decimal(num) / Decimal(den)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def _ratios(summary: dict[str, Any]) -> dict[str, str]:
    """Every count-backed ratio of one ``summarize`` result, rendered once from its counts."""
    sc, al = summary["scenario"], summary["alerts"]
    tp, fp, fn, susp, legit = sc["tp"], sc["fp"], sc["fn"], sc["suspicious"], sc["legitimate"]
    return {
        "precision": _r(tp, tp + fp, sc["precision"]),
        "recall": _r(tp, susp, sc["recall"]),
        "f1": _r(2 * tp, 2 * tp + fp + fn, sc["f1"]),
        "fpr": _r(fp, legit, sc["fpr"]),
        "high_band_recall": _r(sc.get("tp_high"), susp, sc["high_band_recall"]),
        "high_band_fpr": _r(sc.get("fp_high"), legit, sc["high_band_fpr"]),
        "alert_precision": _r(al.get("relevant"), al["flagged"], al["precision"]),
    }


def render(a: dict[str, Any]) -> str:
    labels = {m["id"]: m["label"] for m in a["methods"]}
    lines = [
        "# Evaluation — synthetic benchmark `bench-v1`",
        "",
        "> Generated by `scripts/run_benchmark.py` from `benchmarks/results/bench-v1.json`. Do not edit by hand.",
        "> **All data is synthetic.** These numbers measure behaviour on our own generated scenarios, "
        "not accuracy on real banking data.",
        "",
        f"* Generated: {a['generated_at']} · code `{a['code']['commit'][:12]}`"
        + (" (**dirty tree**)" if a["code"]["dirty"] else " (clean tree)"),
        f"* Generator `{a['generator']['version']}` · detectors `{a['config']['detectors_version']}` · "
        f"policy `{a['config']['policy_version']}` · config sha256 `{a['config']['config_sha256'][:16]}…`",
        f"* Python {a['environment']['python']} · runtime {a['runtime_seconds']} s",
        "",
        "## Protocol",
        "",
        f"* Matching: {a['protocol']['matching_rule']}",
        f"* Flagged: {a['protocol']['flagged']}",
    ]
    lines += [f"* Unit — **{k}**: {v}" for k, v in a["protocol"]["units"].items()]
    lines += ["", "| Split | Seeds | Datasets | Role | Precision mix | Split sha256 |", "|---|---|---:|---|---|---|"]
    for s, info in a["splits"].items():
        mix = ", ".join(f"{k} {v}" for k, v in info["precision_mix"].items())
        lines.append(
            f"| {s} | {info['seeds'][0]}–{info['seeds'][1]} | {info['datasets']} | "
            f"{a['protocol']['splits'][s]} | {mix} | `{info['split_sha256'][:16]}…` |"
        )
    for split, res in a["results"].items():
        lines += [
            "",
            f"## Results — {split}",
            "",
            "| Method | Scen. precision | Scen. recall | F1 | FPR | High-band recall | High-band FPR | "
            "Alerts / dataset | Alert precision | P@5 | Recall@5 | P@10 | Recall@10 | Median ms |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for mid, s in res.items():
            q, r = s["queue"], _ratios(s)
            lines.append(
                f"| {labels.get(mid, mid)} | {r['precision']} | {r['recall']} | {r['f1']} | {r['fpr']} | "
                f"{r['high_band_recall']} | {r['high_band_fpr']} | {_f(s['alerts']['per_dataset'])} | "
                f"{r['alert_precision']} | {_f(q['p_at_5'])} | "
                f"{_f(q['recall_at_5'])} | {_f(q['p_at_10'])} | {_f(q['recall_at_10'])} | "
                f"{_f(s['latency_ms']['median'])} |"
            )
    hold = a["results"].get("holdout") or next(iter(a["results"].values()))
    fams = hold["nexora_v2"]["by_family"]
    lines += [
        "",
        "## Detection by scenario family (holdout)",
        "",
        "Suspicious families: share flagged (higher is better). Legitimate families: share flagged (lower is better).",
        "",
        "| Family | Scenarios | NEXORA v2 | NEXORA v1 | B1 rules |",
        "|---|---:|---:|---:|---:|",
    ]
    for fam, v in fams.items():
        v1 = hold["nexora_v1"]["by_family"].get(fam, {})
        r1 = hold["B1_rules"]["by_family"].get(fam, {})
        lines.append(
            f"| {fam} | {v['total']} | {v['flagged']}/{v['total']} | {v1.get('flagged', 0)}/{v['total']} | "
            f"{r1.get('flagged', 0)}/{v['total']} |"
        )
    for split, abl in a.get("ablations", {}).items():
        lines += [
            "",
            f"## Ablations — {split}",
            "",
            "| Variant | Scen. recall | FPR | High-band FPR | Alert precision | P@5 | Recall@5 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for vid, s in abl.items():
            q, r = s["queue"], _ratios(s)
            lines.append(
                f"| {vid} | {r['recall']} | {r['fpr']} | {r['high_band_fpr']} | "
                f"{r['alert_precision']} | {_f(q['p_at_5'])} | {_f(q['recall_at_5'])} |"
            )
    if "robustness" in a:
        base = a["robustness"]["base"]
        rb = _ratios(base)
        lines += [
            "",
            "## Robustness — validation",
            "",
            "| Perturbation | Identical output | Scen. recall | FPR | High-band FPR | P@5 | Median ms |",
            "|---|---|---:|---:|---:|---:|---:|",
            f"| (none) | — | {rb['recall']} | {rb['fpr']} | {rb['high_band_fpr']} | {_f(base['queue']['p_at_5'])} | "
            f"{_f(base['latency_ms']['median'])} |",
        ]
        for p in a["robustness"]["perturbations"]:
            s, r = p["summary"], _ratios(p["summary"])
            lines.append(
                f"| {p['description']} | {'yes' if p['identical_to_base'] else 'no'} | "
                f"{r['recall']} | {r['fpr']} | {r['high_band_fpr']} | "
                f"{_f(s['queue']['p_at_5'])} | {_f(s['latency_ms']['median'])} |"
            )
        lines += [
            "",
            "## Threshold sensitivity — validation",
            "",
            "| Change | Scen. recall | FPR | High-band FPR | P@5 |",
            "|---|---:|---:|---:|---:|",
        ]
        for v in a["sensitivity"]["variants"]:
            s, r = v["summary"], _ratios(v["summary"])
            lines.append(
                f"| `{v['id']}` | {r['recall']} | {r['fpr']} | {r['high_band_fpr']} | {_f(s['queue']['p_at_5'])} |"
            )
    if "examples" in a:
        lines += ["", "## Error examples — holdout, NEXORA v2", ""]
        for title, key in (
            ("False positives (legitimate, flagged)", "false_positives"),
            ("False negatives", "false_negatives"),
        ):
            lines += [
                f"### {title}",
                "",
                "| Family | Explanation | Kind | Band | Priority | Reason codes |",
                "|---|---|---|---|---:|---|",
            ]
            for r in a["examples"][key]:
                lines.append(
                    f"| {r['family']} | {r['explanation']} | {_f(r['kind'])} | {_f(r['band'])} | {_f(r['priority'])} | "
                    f"{', '.join(r['reasons']) or '—'} |"
                )
            lines.append("")
    lines += ["## Limitations", ""] + [f"* {x}" for x in a["limitations"]] + [""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--splits", default="dev,validation,holdout")
    parser.add_argument("--out", default=str(ROOT / OUTPUTS[0]))
    parser.add_argument("--report", default=str(ROOT / OUTPUTS[1]))
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="re-render the report from the existing artifact (--out) without running the benchmark",
    )
    args = parser.parse_args()
    if args.render_only:
        Path(args.report).write_text(render(json.loads(Path(args.out).read_text(encoding="utf-8"))), encoding="utf-8")
        print(f"rendered {args.report} from {args.out}")
        return
    artifact = run([s.strip() for s in args.splits.split(",") if s.strip()])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    Path(args.report).write_text(render(artifact), encoding="utf-8")
    print(f"wrote {out} and {args.report} in {artifact['runtime_seconds']} s")


if __name__ == "__main__":
    main()
