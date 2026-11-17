"""Read model for the persisted benchmark artifact (spec §19 Screen F).

The API never computes or invents metrics: it serves the JSON written by an executed run
of ``scripts/run_benchmark.py`` and fails loudly when the artifact is missing or malformed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexora.application.errors import AppError, NotFound

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_VERSION = 1


class ArtifactInvalid(AppError):
    status_code = 500


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def load_report(path: str) -> dict[str, Any]:
    file = resolve(path)
    if not file.is_file():
        raise NotFound(
            "BENCHMARK_NOT_FOUND",
            "no benchmark artifact has been produced yet",
            {"command": "uv run python scripts/run_benchmark.py"},
        )
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ArtifactInvalid("BENCHMARK_ARTIFACT_INVALID", "benchmark artifact is not valid JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactInvalid(
            "BENCHMARK_ARTIFACT_INVALID",
            "unsupported benchmark artifact schema",
            {"expected": SCHEMA_VERSION, "found": raw.get("schema_version") if isinstance(raw, dict) else None},
        )
    roles = raw.get("protocol", {}).get("splits", {})
    report = dict(raw)
    report["code"] = {k: raw["code"][k] for k in ("commit", "dirty")}
    report["protocol"] = {k: raw["protocol"][k] for k in ("matching_rule", "flagged", "units")}
    # Per-dataset manifests stay in the artifact for audit; the screen needs split-level identity only.
    report["splits"] = {
        name: {**{k: v for k, v in info.items() if k != "manifest"}, "role": roles.get(name, "")}
        for name, info in raw["splits"].items()
    }
    return report
