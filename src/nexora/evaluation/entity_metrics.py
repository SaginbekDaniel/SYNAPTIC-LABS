"""Entity-level, ranking and calibration metrics (backlog B-041, finding H-12).

All data these metrics are computed on is synthetic; they describe behaviour on generated scenarios only.

* **Accounts** — the classical account-level view: positives are the accounts of planted suspicious scenarios
  (complete truth lists), "flagged" is every account of a flagged item (its accounts and its subject). Counts are
  summed over datasets. False positives are split into accounts of labelled legitimate scenarios and unlabelled
  background accounts, so the reader can see what the denominator contains.
* **Ranking** — the analyst queue as a ranking: every queued item of every dataset, ordered by the queue key
  (band rank, then descending score/priority). Items with an identical key are taken together, as one
  threshold, so the result never depends on how ties happen to be ordered. A step counts *distinct* planted
  networks reached: a second alert on an already reached network adds review work but no new find (the same
  convention as the distinct P@K the harness already reports). The curve stores integer counts only; average
  precision (AP) = Σ Δrecall × precision over the steps, recomputable from the curve.
* **Reliability by band** — for banded methods: the share of items in each band that match a planted suspicious
  scenario, with a Wilson 95 % interval. Priority is a triage order, not a probability (ADR-005); this measures
  how the bands relate to the planted fraction, it does not calibrate them.
* **Bootstrap** — 95 % percentile intervals over datasets resampled with replacement (fixed seed).
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only (benchmark imports this module)
    from nexora.evaluation.benchmark import DatasetEval

Z95 = 1.959963984540054
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261123
BAND_ORDER = ("critical", "high", "medium", "insufficient_evidence", "low")


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials (None when n = 0)."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


# -- accounts --------------------------------------------------------------------------------------
def account_counts(ev: DatasetEval) -> dict[str, int]:
    positive: set[str] = set()
    legitimate: set[str] = set()
    for t in ev.truth:
        (positive if t.label == "suspicious" else legitimate).update(t.accounts)
    legitimate -= positive  # an account in both kinds of scenario counts as positive
    flagged: set[str] = set()
    for item in ev.items:
        if item.flagged:
            flagged.update(item.accounts)
            flagged.add(item.subject)
    tp = len(flagged & positive)
    fp_legit = len(flagged & legitimate)
    return {
        "positive": len(positive),
        "flagged": len(flagged),
        "tp": tp,
        "fp": len(flagged) - tp,
        "fn": len(positive) - tp,
        "fp_labelled_legitimate": fp_legit,
        "fp_unlabelled": len(flagged) - tp - fp_legit,
    }


def accounts(evals: Sequence[DatasetEval]) -> dict[str, Any]:
    total: dict[str, int] = defaultdict(int)
    for ev in evals:
        for k, v in account_counts(ev).items():
            total[k] += v
    return {
        **{k: total[k] for k in ("positive", "flagged", "tp", "fp", "fn", "fp_labelled_legitimate", "fp_unlabelled")},
        "recall": _ratio(total["tp"], total["positive"]),
        "precision": _ratio(total["tp"], total["flagged"]),
    }


# -- ranking ---------------------------------------------------------------------------------------
def ranking(evals: Sequence[DatasetEval]) -> dict[str, Any]:
    """Distinct-network precision–recall over the pooled queue, ties grouped; AP from the steps."""
    total = sum(1 for ev in evals for t in ev.truth if t.label == "suspicious")
    groups: dict[tuple[int, float], list[tuple[int, str] | None]] = defaultdict(list)
    queued = 0
    for d, ev in enumerate(evals):
        for item, m in zip(ev.items, ev.matches, strict=True):
            if not item.queued:
                continue
            queued += 1
            hit = (d, m.scenario_id) if m is not None and m.label == "suspicious" else None
            groups[(item.band_rank, -item.score)].append(hit)
    reached: set[tuple[int, str]] = set()
    seen = 0
    curve: list[dict[str, int]] = []
    ap = 0.0
    for key in sorted(groups):
        group = groups[key]
        seen += len(group)
        before = len(reached)
        reached.update(h for h in group if h is not None)
        if len(reached) > before:
            curve.append({"items": seen, "networks": len(reached)})
            ap += (len(reached) - before) / total * len(reached) / seen if total else 0.0
    return {
        "suspicious_networks": total,
        "queued_items": queued,
        "networks_reached": len(reached),
        "average_precision": round(ap, 4) if total else None,
        "curve": curve,
    }


def average_precision_from_curve(curve: Sequence[dict[str, int]], total: int) -> float | None:
    """AP recomputed from the stored integer curve (artifact-consistency checks)."""
    if total == 0:
        return None
    ap, prev = 0.0, 0
    for p in curve:
        ap += (p["networks"] - prev) / total * p["networks"] / p["items"]
        prev = p["networks"]
    return round(ap, 4)


# -- reliability -----------------------------------------------------------------------------------
def reliability(evals: Sequence[DatasetEval]) -> list[dict[str, Any]] | None:
    """Planted share per band (all assessed items, alerted or not); None for unbanded methods."""
    counts: dict[str, list[int]] = {}
    for ev in evals:
        for item, m in zip(ev.items, ev.matches, strict=True):
            if item.band is None:
                continue
            c = counts.setdefault(item.band, [0, 0])
            c[0] += 1
            c[1] += m is not None and m.label == "suspicious"
    if not counts:
        return None
    rows = []
    for band in [b for b in BAND_ORDER if b in counts] + sorted(set(counts) - set(BAND_ORDER)):
        n, k = counts[band]
        interval = wilson(k, n)
        rows.append(
            {
                "band": band,
                "items": n,
                "planted": k,
                "share": _ratio(k, n),
                "wilson95": list(interval) if interval else None,
            }
        )
    return rows


# -- bootstrap -------------------------------------------------------------------------------------
def _percentile(sorted_values: Sequence[float], q: float) -> float:
    idx = q * (len(sorted_values) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (idx - lo)


def bootstrap(evals: Sequence[DatasetEval], draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """95 % percentile intervals over datasets resampled with replacement."""
    metrics: dict[str, Callable[[list[DatasetEval]], float | None]] = {
        "account_recall": lambda e: accounts(e)["recall"],
        "account_precision": lambda e: accounts(e)["precision"],
        "average_precision": lambda e: ranking(e)["average_precision"],
    }
    out: dict[str, Any] = {"draws": draws, "seed": seed}
    if not evals:
        return {**out, **{k: None for k in metrics}}
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {k: [] for k in metrics}
    n = len(evals)
    for _ in range(draws):
        resample = [evals[rng.randrange(n)] for _ in range(n)]
        for name, fn in metrics.items():
            v = fn(resample)
            if v is not None:
                samples[name].append(v)
    for name, values in samples.items():
        values.sort()
        out[name] = [round(_percentile(values, 0.025), 4), round(_percentile(values, 0.975), 4)] if values else None
    return out


def entity_summary(evals: Sequence[DatasetEval], *, with_bootstrap: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {"accounts": accounts(evals), "ranking": ranking(evals), "reliability": reliability(evals)}
    if with_bootstrap:
        out["bootstrap"] = bootstrap(evals)
    return out
