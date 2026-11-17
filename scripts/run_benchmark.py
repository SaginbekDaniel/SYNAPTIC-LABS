"""Run the NEXORA synthetic benchmark and write reproducible report artifacts.

Examples::

    uv run python scripts/run_benchmark.py --label baseline-v1 --splits dev val
    uv run python scripts/run_benchmark.py --label final --splits dev val test --include-test --experiments

The untouched test split is evaluated only with ``--include-test``. Tuning decisions must be
made on ``dev`` (and checked on ``val``); see docs/EVALUATION.md for the protocol.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nexora.evaluation.benchmark.methods import default_methods
from nexora.evaluation.benchmark.runner import evaluate, write_report
from nexora.evaluation.benchmark.suite import build_suite

RESULTS = Path(__file__).resolve().parents[1] / "benchmarks" / "results"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", required=True, help="run label; also the output directory name")
    parser.add_argument("--splits", nargs="+", default=["dev", "val"], choices=["dev", "val", "test"])
    parser.add_argument("--include-test", action="store_true", help="required to evaluate the held-out test split")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--no-v2", action="store_true", help="evaluate baselines and the frozen v1 engine only")
    parser.add_argument("--experiments", action="store_true", help="also run ablations and robustness tests")
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()
    if "test" in args.splits and not args.include_test:
        parser.error("the test split is sealed; pass --include-test deliberately (see docs/EVALUATION.md)")

    splits = tuple(dict.fromkeys(["dev", *args.splits]))  # dev is always built: baselines are fitted on it
    suite = build_suite(master_seed=args.seed, splits=splits)  # type: ignore[arg-type]
    methods = default_methods(include_v2=not args.no_v2)
    nexora = [m.name for m in methods if m.group == "nexora"]
    extra = {}
    if args.experiments:
        from nexora.evaluation.benchmark.experiments import run_experiments

        extra = run_experiments(suite, split="test" if "test" in args.splits else "val")
    report, raw = evaluate(
        suite,
        methods,
        splits=args.splits,
        label=args.label,
        ttd_methods=nexora,
        example_methods=nexora,
        extra=extra,
    )
    out_dir = args.out / args.label
    write_report(report, raw, out_dir)
    index_path = args.out / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"runs": []}
    index["runs"] = [r for r in index["runs"] if r["label"] != args.label] + [
        {
            "label": args.label,
            "created_at": report["run"]["created_at"],
            "code_commit": report["run"]["code_commit"],
            "splits": report["run"]["splits_evaluated"],
            "path": f"{args.label}/report.json",
        }
    ]
    index["latest"] = args.label
    index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
