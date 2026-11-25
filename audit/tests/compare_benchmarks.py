"""Compare published classification outputs with clean-checkout reruns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

VARIABLE = {
    "latency_ms",
    "generated_at",
    "runtime_seconds",
    "environment",
    "code",
    "git_commit",
    "git_worktree_dirty",
}
FILES = {
    "bench_v1": ("benchmarks/results/bench-v1.json", "bench-v1-rerun.json"),
    "transfer_holdout": ("benchmarks/transfer_protection/results/holdout-v1.json", "transfer-holdout-rerun.json"),
}


def stable(value):
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key not in VARIABLE}
    if isinstance(value, list):
        return [stable(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    results = {}
    for name, (published_path, rerun_path) in FILES.items():
        published = json.loads((args.repo / published_path).read_text())
        rerun = json.loads((args.evidence / rerun_path).read_text())
        before, after = stable(published), stable(rerun)
        mismatches = sorted(key for key in (before.keys() | after.keys()) if before.get(key) != after.get(key))
        results[name] = {
            "matches": not mismatches,
            "mismatched_top_level_fields": mismatches,
            "published_commit": published.get("git_commit") or published.get("code", {}).get("commit"),
            "rerun_commit": rerun.get("git_commit") or rerun.get("code", {}).get("commit"),
        }
    result = {"ignored_metadata_keys": sorted(VARIABLE), "results": results}
    print(json.dumps(result, indent=2))
    return int(not all(row["matches"] for row in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
