"""Matching rule and metrics. Each metric names its evaluation unit; units are never mixed.

Units
-----
* **scenario** (primary): one planted scenario per network. A positive network is a true
  positive when at least one *raised* prediction matches its planted scenario; a negative
  network is a false positive when a raised prediction matches its planted benign scenario.
* **alert**: every raised prediction. It is "true" only when it matches a planted
  *suspicious* scenario; alerts on benign scenarios and on unlabelled background are false.
* **queue** (ranking): all raised predictions of a split pooled and ordered by review score;
  Precision@K / Recall@K count *distinct* suspicious scenarios (duplicates waste a slot).
* **account**: union of accounts in raised predictions vs. accounts of planted suspicious
  scenarios. Reported separately because it over-counts one network as many hits.

Matching rule (fixed before any measurement): a prediction matches a scenario when at least
half of its accounts belong to the scenario *and* — if the prediction cites transactions — at
least one cited transaction is a planted scenario transaction.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any

from nexora.evaluation.benchmark.methods import MethodResult, Prediction
from nexora.evaluation.benchmark.scenarios import TruthRecord

MATCH_MIN_ACCOUNT_SHARE = 0.5
K_VALUES = (10, 25, 50, 100)
BOOTSTRAP_REPS = 1000
BOOTSTRAP_SEED = 2026


def matches(pred: Prediction, truth: TruthRecord) -> bool:
    accounts = set(pred.accounts)
    if not accounts:
        return False
    if len(accounts & set(truth.accounts)) / len(accounts) < MATCH_MIN_ACCOUNT_SHARE:
        return False
    if pred.source_tx_ids:
        return bool(set(pred.source_tx_ids) & set(truth.transaction_ids))
    return True


@dataclass
class NetworkOutcome:
    network_id: str
    split: str
    family: str
    variant: str
    label: str
    difficulty: str
    expected: str
    outcome: str  # TP / FN / FP / TN at the scenario unit
    reason: str
    raised: int
    raised_suspicious: int
    raised_benign_scenario: int
    raised_background: int
    duplicate_raised: int
    abstained_on_scenario: bool
    acc_tp: int
    acc_fp: int
    acc_fn: int
    acc_tn: int
    latency_ms: float
    n_transactions: int
    partial: bool
    scenario_alerts: list[dict[str, Any]] = field(default_factory=list)


def score_network(split: str, truth: TruthRecord, result: MethodResult, all_accounts: set[str]) -> NetworkOutcome:
    raised = [p for p in result.predictions if p.status == "raised"]
    on_scenario = [p for p in raised if matches(p, truth)]
    abstained = any(p.status == "abstained" and matches(p, truth) for p in result.predictions)
    below = any(p.status == "below" and matches(p, truth) for p in result.predictions)
    suspicious = truth.label == "suspicious"
    if suspicious:
        outcome = "TP" if on_scenario else "FN"
        if on_scenario:
            reason = "detected:" + "+".join(sorted({p.kind for p in on_scenario}))
        elif abstained:
            reason = "abstained"
        elif below:
            reason = "below_alert_band"
        else:
            reason = "no_candidate"
    else:
        outcome = "FP" if on_scenario else "TN"
        reason = ("alerted:" + "+".join(sorted({p.kind for p in on_scenario}))) if on_scenario else "no_alert"
    flagged = {a for p in raised for a in p.accounts}
    positives = set(truth.accounts) if suspicious else set()
    universe = all_accounts | flagged
    acc_tp = len(flagged & positives)
    acc_fp = len(flagged - positives)
    acc_fn = len(positives - flagged)
    ordered = sorted(on_scenario, key=lambda p: -(p.score or 0.0))
    return NetworkOutcome(
        network_id=truth.network_id,
        split=split,
        family=truth.family,
        variant=truth.variant,
        label=truth.label,
        difficulty=truth.difficulty,
        expected=truth.expected,
        outcome=outcome,
        reason=reason,
        raised=len(raised),
        raised_suspicious=len(on_scenario) if suspicious else 0,
        raised_benign_scenario=0 if suspicious else len(on_scenario),
        raised_background=len(raised) - len(on_scenario),
        duplicate_raised=max(0, len(on_scenario) - 1),
        abstained_on_scenario=abstained,
        acc_tp=acc_tp,
        acc_fp=acc_fp,
        acc_fn=acc_fn,
        acc_tn=len(universe) - acc_tp - acc_fp - acc_fn,
        latency_ms=round(result.latency_ms, 3),
        n_transactions=result.n_transactions,
        partial=bool(result.partial_reasons),
        scenario_alerts=[
            {"kind": p.kind, "band": p.band, "score": p.score, "reasons": list(p.reasons)} for p in ordered[:3]
        ],
    )


def ratio(num: int, den: int) -> float | None:
    """``None`` (undefined) instead of 0 or 1 when the denominator is zero (spec §19.3)."""
    return round(num / den, 4) if den else None


def f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None or p + r == 0:
        return None if p is None or r is None else 0.0
    return round(2 * p * r / (p + r), 4)


def confusion(outcomes: Sequence[NetworkOutcome]) -> dict[str, Any]:
    c = Counter(o.outcome for o in outcomes)
    tp, fp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1(precision, recall),
        "fpr": ratio(fp, fp + tn),
        "fnr": ratio(fn, fn + tp),
    }


def bootstrap_ci(outcomes: Sequence[NetworkOutcome]) -> dict[str, list[float] | None]:
    """95 % percentile intervals, resampling whole networks stratified by label."""
    pos = [o for o in outcomes if o.label == "suspicious"]
    neg = [o for o in outcomes if o.label != "suspicious"]
    rng = random.Random(BOOTSTRAP_SEED)
    samples: dict[str, list[float]] = defaultdict(list)
    for _ in range(BOOTSTRAP_REPS):
        draw = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
        m = confusion(draw)
        for key in ("precision", "recall", "f1", "fpr"):
            if m[key] is not None:
                samples[key].append(m[key])
    out: dict[str, list[float] | None] = {}
    for key in ("precision", "recall", "f1", "fpr"):
        vals = sorted(samples[key])
        if len(vals) < BOOTSTRAP_REPS * 0.9:
            out[key] = None
            continue
        out[key] = [round(vals[int(0.025 * (len(vals) - 1))], 4), round(vals[int(0.975 * (len(vals) - 1))], 4)]
    return out


def queue_metrics(
    ranked: Sequence[tuple[float, str, Prediction, TruthRecord]], n_positive: int
) -> dict[str, dict[str, Any]]:
    """Precision@K / Recall@K over distinct suspicious scenarios in a pooled review queue."""
    order = sorted(ranked, key=lambda r: (-r[0], r[1], r[2].pred_id))
    seen: set[str] = set()
    hits_at: list[int] = []
    for _, _, pred, truth in order:
        if truth.label == "suspicious" and truth.network_id not in seen and matches(pred, truth):
            seen.add(truth.network_id)
        hits_at.append(len(seen))
    out: dict[str, dict[str, Any]] = {}
    for k in K_VALUES:
        hits = hits_at[min(k, len(hits_at)) - 1] if hits_at else 0
        out[str(k)] = {"precision": round(hits / k, 4), "recall": ratio(hits, n_positive), "hits": hits}
    return out


def summarise(
    outcomes: Sequence[NetworkOutcome],
    ranked: Sequence[tuple[float, str, Prediction, TruthRecord]],
) -> dict[str, Any]:
    n = len(outcomes)
    n_pos = sum(1 for o in outcomes if o.label == "suspicious")
    raised = sum(o.raised for o in outcomes)
    true_alerts = sum(o.raised_suspicious for o in outcomes)
    lat = sorted(o.latency_ms for o in outcomes)
    tx = sum(o.n_transactions for o in outcomes)
    acc = {k: sum(getattr(o, f"acc_{k}") for o in outcomes) for k in ("tp", "fp", "fn", "tn")}
    by_family: dict[str, Any] = {}
    for fam in sorted({o.family for o in outcomes}):
        fo = [o for o in outcomes if o.family == fam]
        positive = fo[0].label == "suspicious"
        hits = sum(1 for o in fo if o.outcome in ("TP", "FP"))
        by_family[fam] = {
            "label": fo[0].label,
            "networks": len(fo),
            "rate": ratio(hits, len(fo)),
            "rate_kind": "detection_rate" if positive else "false_positive_rate",
            "alerts_per_network": round(sum(o.raised for o in fo) / len(fo), 3),
            "abstained": sum(1 for o in fo if o.abstained_on_scenario and o.outcome in ("FN", "TN")),
            "reasons": dict(Counter(o.reason for o in fo)),
            "by_variant": {
                v: ratio(sum(1 for o in fo if o.variant == v and o.outcome in ("TP", "FP")), len(vo))
                for v in sorted({o.variant for o in fo})
                if (vo := [o for o in fo if o.variant == v])
            },
        }
    by_difficulty = {
        d: confusion([o for o in outcomes if o.difficulty == d]) for d in sorted({o.difficulty for o in outcomes})
    }
    return {
        "unit_scenario": {**confusion(outcomes), "ci95": bootstrap_ci(outcomes)},
        "unit_alert": {
            "raised": raised,
            "true_alerts": true_alerts,
            "precision": ratio(true_alerts, raised),
            "on_benign_scenarios": sum(o.raised_benign_scenario for o in outcomes),
            "on_background": sum(o.raised_background for o in outcomes),
            "duplicates_of_detected_scenario": sum(o.duplicate_raised for o in outcomes),
            "alerts_per_network": round(raised / n, 3) if n else None,
            "alerts_per_1000_transactions": round(1000 * raised / tx, 3) if tx else None,
            "background_alerts_per_network": round(sum(o.raised_background for o in outcomes) / n, 3) if n else None,
        },
        "unit_queue": queue_metrics(ranked, n_pos),
        "unit_account": {
            **acc,
            "precision": ratio(acc["tp"], acc["tp"] + acc["fp"]),
            "recall": ratio(acc["tp"], acc["tp"] + acc["fn"]),
            "fpr": ratio(acc["fp"], acc["fp"] + acc["tn"]),
        },
        "by_family": by_family,
        "by_difficulty": by_difficulty,
        "abstentions": {
            "on_suspicious": sum(1 for o in outcomes if o.label == "suspicious" and o.reason == "abstained"),
            "on_benign": sum(1 for o in outcomes if o.label != "suspicious" and o.abstained_on_scenario),
        },
        "latency_ms": {
            "median": round(median(lat), 2) if lat else None,
            "p95": round(lat[int(0.95 * (len(lat) - 1))], 2) if lat else None,
            "max": round(lat[-1], 2) if lat else None,
            "per_1000_transactions": round(1000 * sum(lat) / tx, 2) if tx else None,
        },
        "partial_networks": sum(1 for o in outcomes if o.partial),
        "networks": n,
        "transactions": tx,
    }


def best_f1_threshold(scenario_scores: Sequence[tuple[bool, float | None]]) -> tuple[float, float]:
    """Threshold maximising scenario-level F1; ties prefer the stricter threshold."""
    candidates = sorted({s for _, s in scenario_scores if s is not None}, reverse=True)
    best = (-1.0, float("inf"))
    for tau in candidates:
        tp = sum(1 for pos, s in scenario_scores if pos and s is not None and s >= tau)
        fp = sum(1 for pos, s in scenario_scores if not pos and s is not None and s >= tau)
        fn = sum(1 for pos, _ in scenario_scores if pos) - tp
        p, r = ratio(tp, tp + fp), ratio(tp, tp + fn)
        value = f1(p, r) or 0.0
        if value > best[0]:
            best = (value, tau)
    return best


def outcome_dict(o: NetworkOutcome) -> dict[str, Any]:
    return asdict(o)
