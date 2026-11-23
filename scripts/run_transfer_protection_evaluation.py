"""Write the JSON report and print a human-readable comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nexora.evaluation.transfer_protection import HOLDOUT, evaluate


def percent(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "n/a"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=HOLDOUT)
    parser.add_argument("--output", type=Path, default=Path("artifacts/transfer-protection-evaluation.json"))
    args = parser.parse_args()
    report = evaluate(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['dataset_version']} | policy {report['policy_version']} | Git {report['git_commit']}")
    print(
        f"Intents: {report['scenario_count']} ({report['legitimate_count']} legitimate, {report['fraud_count']} fraud)"
    )
    print(f"{'method':<22} {'TP FP TN FN':<15}  {'precision':>10} {'recall':>8} {'FPR':>8} {'FP/1000':>9}")
    for name, result in report["results"].items():
        counts = " ".join(f"{result[key]:2}" for key in ("tp", "fp", "tn", "fn"))
        fp_per_1000 = result["false_warnings_per_1000_legitimate"]
        fp_text = f"{fp_per_1000:.1f}" if fp_per_1000 is not None else "n/a"
        print(
            f"{name:<22} {counts:<15}  {percent(result['precision']):>10} "
            f"{percent(result['recall']):>8} {percent(result['false_positive_rate']):>8} {fp_text:>9}"
        )
        latency = " / ".join(f"{value:.4f}" if value is not None else "n/a" for value in result["latency_ms"].values())
        print(
            f"  LIMITED_SIGNAL {percent(result['limited_signal_rate'])} | "
            f"UNAVAILABLE {percent(result['unavailable_rate'])} | p50/p95/p99 {latency} ms"
        )
    for limitation in report["limitations"]:
        print(limitation)
    print(f"JSON report: {args.output}")


if __name__ == "__main__":
    main()
