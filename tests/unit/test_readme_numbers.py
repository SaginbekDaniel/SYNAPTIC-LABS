"""Every benchmark figure quoted in README.md is recomputed from its committed artifact (backlog B-004).

The README quotes two runs: configuration v2 on the exposed ``bench-v1`` holdout (what the live demo and the
pitch show) and the shipped configuration on the pre-registered ``sealed-v2`` split. If an artifact is
regenerated, these tests fail until the README is updated - figures are never typed from memory.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _artifact(name: str) -> dict:
    return json.loads((ROOT / "benchmarks" / "results" / name).read_text(encoding="utf-8"))


def _pct(num: int, den: int) -> str:
    """Percent with one decimal, half-up on the exact ratio (never on a pre-rounded stored ratio)."""
    return str((Decimal(100 * num) / Decimal(den)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _recall(s: dict) -> str:
    return f"{_pct(s['tp'], s['tp'] + s['fn'])} % ({s['tp']}/{s['tp'] + s['fn']})"


def _flagged(s: dict) -> str:
    return f"{_pct(s['fp'], s['fp'] + s['tn'])} % ({s['fp']}/{s['fp'] + s['tn']})"


def test_bench_v1_holdout_figures_match_the_artifact() -> None:
    art = _artifact("bench-v1.json")
    assert art["config"]["policy_version"] == "risk-policy-v2"  # the README labels this table "NEXORA v2"
    nx, rules = art["results"]["holdout"]["nexora_v2"], art["results"]["holdout"]["B1_rules"]
    row_flag = f"| {_flagged(rules['scenario'])} | {_flagged(nx['scenario'])} |"
    row_recall = f"| {_recall(rules['scenario'])} | {_recall(nx['scenario'])} |"
    assert row_flag in README
    assert row_recall in README
    alerts = f"| {Decimal(str(rules['alerts']['per_dataset'])).quantize(Decimal('0.1'), ROUND_HALF_UP)} | "
    assert alerts + f"{nx['alerts']['per_dataset']} |" in README
    ratio = (Decimal(str(rules["alerts"]["per_dataset"])) / Decimal(str(nx["alerts"]["per_dataset"]))).quantize(
        Decimal("0.1"), ROUND_HALF_UP
    )
    assert f"queue is {ratio}× shorter" in README
    s_nx, s_rules = nx["scenario"], rules["scenario"]
    assert f"{s_nx['tp']} of {s_nx['tp'] + s_nx['fn']} against the rules' {s_rules['tp']} of" in README
    assert f"{s_nx['fn']} misses" in README
    assert f"artifact commit `{art['code']['commit'][:7]}`" in README
    assert art["splits"]["holdout"]["datasets"] == 30 and "30 synthetic datasets" in README


def test_sealed_v2_figures_match_the_artifact() -> None:
    art = _artifact("sealed-v2-evaluation.json")
    assert art["decision"]["outcome"] == "improvement"  # README: "answered yes"
    res = art["results"]
    rules, v2, v3 = res["B1_rules"], res["baseline_v2"], res["candidate"]
    assert (
        f"| {rules['alerts']['per_dataset']} | {v2['alerts']['per_dataset']} | {v3['alerts']['per_dataset']} |"
        in README
    )
    assert f"| {_flagged(rules['scenario'])} | {_flagged(v2['scenario'])} | {_flagged(v3['scenario'])} |" in README
    assert f"| {_recall(rules['scenario'])} | {_recall(v2['scenario'])} | {_recall(v3['scenario'])} |" in README
    assert f"{art['datasets']} datasets" in README


def test_readme_names_the_configuration_this_branch_ships() -> None:
    detectors = (ROOT / "configs" / "detectors.yaml").read_text(encoding="utf-8")
    policy = (ROOT / "configs" / "risk_policy.yaml").read_text(encoding="utf-8")
    assert "version: detectors-v3" in detectors and "version: risk-policy-v3" in policy
    assert "`detectors-v3`, `risk-policy-v3`" in README
