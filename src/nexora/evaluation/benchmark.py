"""Reproducible benchmark over the synthetic ``bench-v1`` suite (spec §15).

Evaluation units (never mixed):

* **Review item** — one entry in an analyst queue: a NEXORA alert (formation) or, for
  account-ranking baselines, one account. An item is *relevant* when it matches a
  planted suspicious scenario.
* **Scenario** — one planted network (suspicious or legitimate). A scenario is
  *flagged* when at least one flagged item matches it. Scenario-level precision, recall,
  F1, FPR and FNR use only scenario counts.

Matching rule (fixed before any measurement): an item matches the scenario that
contains the item's subject account and shares the most accounts with the item, with at
least ``min(2, |item accounts|)`` shared accounts. Scenarios never share accounts.

Ground truth is consumed only here, after detection; detectors receive the same
canonical transfers the runtime would ingest (ADR-009).
"""

from __future__ import annotations

import copy
import random
import statistics
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import networkx as nx

from nexora.analytics.config import AnalysisConfig
from nexora.analytics.graph_builder import build_snapshot
from nexora.analytics.pipeline import AnalysisOutput, run_analysis
from nexora.analytics.risk import opens_alert
from nexora.domain.ids import canonical_json, sha256_hex, transaction_uuid
from nexora.domain.transfers import ObservedTransfer
from nexora.evaluation.generator import GeneratedDataset, ScenarioTruth, generate
from nexora.evaluation.sealed_generator import generate_sealed
from nexora.ingest.validation import prepare_batch

BENCHMARK_VERSION = "bench-harness-v1"
SUITE = "bench-v1"
#: Seed ranges per split. ``holdout`` is reported once, after all design decisions.
SPLITS: dict[str, tuple[int, ...]] = {
    "dev": tuple(range(1000, 1030)),
    "validation": tuple(range(2000, 2020)),
    "holdout": tuple(range(3000, 3030)),
    # Sealed final evaluation (docs/evaluation/EXPERIMENT_PROTOCOL.md): independent generator
    # ``sealed-gen-v1``, evaluated once after the configuration and this harness were locked.
    "sealed": tuple(range(9000, 9060)),
}
#: Splits whose results have been inspected during development; reported, never tuned on again.
EXPOSED_SPLITS = frozenset({"dev", "validation", "holdout"})
BAND_RANK = {"critical": 0, "high": 1, "medium": 2, "insufficient_evidence": 3, "low": 4}
FLAG_BANDS = frozenset({"critical", "high", "medium"})
HIGH_BANDS = frozenset({"critical", "high"})
QUEUE_KS = (5, 10)


# ---------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------
def dataset_id_for(ds: GeneratedDataset) -> str:
    return f"bench:{ds.suite}:{ds.seed}:{ds.precision}"


def to_transfers(rows: list[dict[str, str]], dataset_id: str) -> list[ObservedTransfer]:
    """Run rows through the production row validation and dedup, exactly like ingestion."""
    records, _report = prepare_batch(list(enumerate(rows, start=1)), source_id="synthetic:bench", is_synthetic=True)
    return [
        ObservedTransfer(
            transaction_id=transaction_uuid(dataset_id, r.source_id, r.source_transaction_id),
            source_transaction_id=r.source_transaction_id,
            sender=r.sender_account_id,
            receiver=r.receiver_account_id,
            amount_minor=r.amount_minor,
            currency=r.currency,
            observed_date=r.observed_date,
            occurred_at=r.occurred_at,
            precision=r.time_precision,
            status=r.status,  # type: ignore[arg-type]
        )
        for r in records
    ]


# ---------------------------------------------------------------------------------------
# Review items and matching
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ReviewItem:
    subject: str
    accounts: frozenset[str]
    score: float  # higher = reviewed earlier (after band rank)
    band_rank: int = 0
    flagged: bool = True
    queued: bool = True  # False: assessed but not alerted (kept only to explain misses)
    kind: str = "account"
    band: str | None = None
    priority: int | None = None
    reasons: tuple[str, ...] = ()
    item_id: str = ""

    @property
    def sort_key(self) -> tuple[int, float, str]:
        return (self.band_rank, -self.score, self.item_id or self.subject)


def match(item: ReviewItem, truth: list[ScenarioTruth]) -> ScenarioTruth | None:
    best: ScenarioTruth | None = None
    best_overlap = 0
    need = min(2, len(item.accounts))
    for t in truth:
        accounts = set(t.accounts)
        if item.subject not in accounts:
            continue
        overlap = len(item.accounts & accounts)
        if overlap >= need and overlap > best_overlap:
            best, best_overlap = t, overlap
    return best


# ---------------------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------------------
@dataclass
class MethodResult:
    items: list[ReviewItem]
    seconds: float
    output: AnalysisOutput | None = None


Method = Callable[[list[ObservedTransfer], dict[str, Any], str], MethodResult]


def nexora_items(out: AnalysisOutput, policy: dict[str, Any]) -> list[ReviewItem]:
    by_formation = {f.id: f for f in out.formations}
    items: list[ReviewItem] = []
    for a in out.assessments:
        alerted = opens_alert(a.band, policy)
        f = by_formation[a.formation_id]
        items.append(
            ReviewItem(
                subject=f.subject_account_id,
                accounts=frozenset((*f.member_ids, *f.exit_ids)),
                score=float(a.priority if a.priority is not None else -1),
                band_rank=BAND_RANK[a.band],
                flagged=alerted and a.band in FLAG_BANDS,
                queued=alerted,
                kind=f.kind,
                band=a.band,
                priority=a.priority,
                reasons=tuple(r.code for r in a.reason_codes),
                item_id=f.id,
            )
        )
    return items


def nexora_method(config: AnalysisConfig) -> Method:
    def run(transfers: list[ObservedTransfer], contract: dict[str, Any], dataset_id: str) -> MethodResult:
        t0 = time.perf_counter()
        out = run_analysis(dataset_id=dataset_id, transfers=transfers, contract=contract, config=config)
        elapsed = time.perf_counter() - t0
        return MethodResult(items=nexora_items(out, config.risk_policy), seconds=elapsed, output=out)

    return run


def structure_only_method(config: AnalysisConfig) -> Method:
    """B3: every structural formation is an alert, ranked by structural strength only."""

    def run(transfers: list[ObservedTransfer], contract: dict[str, Any], dataset_id: str) -> MethodResult:
        t0 = time.perf_counter()
        out = run_analysis(dataset_id=dataset_id, transfers=transfers, contract=contract, config=config)
        strength = {s.formation_id: s.strength or 0.0 for s in out.signals if s.family == "STRUCTURE"}
        items = [
            ReviewItem(
                subject=f.subject_account_id,
                accounts=frozenset((*f.member_ids, *f.exit_ids)),
                score=strength.get(f.id, 0.0),
                kind=f.kind,
                item_id=f.id,
            )
            for f in out.formations
        ]
        return MethodResult(items=items, seconds=time.perf_counter() - t0)

    return run


def _account_items(scores: dict[str, float], flagged: set[str] | None = None) -> list[ReviewItem]:
    return [
        ReviewItem(subject=a, accounts=frozenset((a,)), score=s, flagged=flagged is None or a in flagged, item_id=a)
        for a, s in scores.items()
    ]


def volume_method(transfers: list[ObservedTransfer], contract: dict[str, Any], dataset_id: str) -> MethodResult:
    """B0: rank accounts by total observed turnover (in + out)."""
    t0 = time.perf_counter()
    snap = build_snapshot(transfers)
    scores: dict[str, float] = defaultdict(float)
    for cg in snap.by_currency.values():
        for acc, m in cg.metrics.items():
            scores[acc] += float(m.incoming_minor + m.outgoing_minor)
    return MethodResult(items=_account_items(dict(scores)), seconds=time.perf_counter() - t0)


def pagerank_method(transfers: list[ObservedTransfer], contract: dict[str, Any], dataset_id: str) -> MethodResult:
    """B2: amount-weighted PageRank, scaled by node count (1.0 = uniform share)."""
    t0 = time.perf_counter()
    snap = build_snapshot(transfers)
    scores: dict[str, float] = defaultdict(float)
    for cg in snap.by_currency.values():
        g = cg.graph
        if g.number_of_nodes() == 0:
            continue
        pr = weighted_pagerank(g)
        n = g.number_of_nodes()
        for acc, v in pr.items():
            scores[acc] = max(scores[acc], v * n)
    return MethodResult(items=_account_items(dict(scores)), seconds=time.perf_counter() - t0)


def weighted_pagerank(
    g: nx.DiGraph, alpha: float = 0.85, iterations: int = 100, tol: float = 1e-10
) -> dict[str, float]:
    """Amount-weighted PageRank by power iteration (pure Python; dangling mass spread uniformly)."""
    nodes = sorted(g.nodes)
    n = len(nodes)
    out_w = {u: sum(int(d["amount_minor"]) for _, _, d in g.out_edges(u, data=True)) for u in nodes}
    rank = dict.fromkeys(nodes, 1.0 / n)
    for _ in range(iterations):
        dangling = sum(rank[u] for u in nodes if out_w[u] == 0)
        new = dict.fromkeys(nodes, (1.0 - alpha) / n + alpha * dangling / n)
        for u in nodes:
            if out_w[u] == 0:
                continue
            share = alpha * rank[u] / out_w[u]
            for _, v, d in g.out_edges(u, data=True):
                new[v] += share * int(d["amount_minor"])
        delta = sum(abs(new[u] - rank[u]) for u in nodes)
        rank = new
        if delta < tol:
            break
    return rank


RULE_WINDOW_DAYS = 3
RULE_FAN_COUNT = 4
RULE_LARGE_MINOR = 200_000_000  # 2 000 000.00 KZT
RULE_PASS_DAYS = 2
RULE_PASS_SHARE_PCT = 80


def rules_method(transfers: list[ObservedTransfer], contract: dict[str, Any], dataset_id: str) -> MethodResult:
    """B1: classic per-account monitoring rules (fan-in/out velocity, large amount, pass-through).

    Flags an account when any rule fires; ranks by number of fired rules, then turnover.
    """
    t0 = time.perf_counter()
    eligible = [t for t in transfers if t.eligible and not t.is_self_transfer]
    inc: dict[str, list[ObservedTransfer]] = defaultdict(list)
    outg: dict[str, list[ObservedTransfer]] = defaultdict(list)
    for t in eligible:
        inc[t.receiver].append(t)
        outg[t.sender].append(t)

    def fan(txs: list[ObservedTransfer], key: Callable[[ObservedTransfer], str]) -> bool:
        txs = sorted(txs, key=lambda t: t.observed_date)
        for i, t in enumerate(txs):
            end = t.observed_date + timedelta(days=RULE_WINDOW_DAYS - 1)
            if len({key(x) for x in txs[i:] if x.observed_date <= end}) >= RULE_FAN_COUNT:
                return True
        return False

    fired: dict[str, int] = defaultdict(int)
    turnover: dict[str, float] = defaultdict(float)
    for acc in set(inc) | set(outg):
        n = 0
        n += fan(inc.get(acc, []), lambda t: t.sender)
        n += fan(outg.get(acc, []), lambda t: t.receiver)
        n += any(t.amount_minor >= RULE_LARGE_MINOR for t in (*inc.get(acc, []), *outg.get(acc, [])))
        for t_in in inc.get(acc, []):
            window_end = t_in.observed_date + timedelta(days=RULE_PASS_DAYS)
            out_sum = sum(
                o.amount_minor
                for o in outg.get(acc, [])
                if t_in.observed_date <= o.observed_date <= window_end and o.currency == t_in.currency
            )
            if out_sum * 100 >= t_in.amount_minor * RULE_PASS_SHARE_PCT:
                n += 1
                break
        fired[acc] = n
        turnover[acc] = float(sum(t.amount_minor for t in (*inc.get(acc, []), *outg.get(acc, []))))
    scores = {a: fired[a] * 1e18 + turnover[a] for a in fired}
    flagged = {a for a, n in fired.items() if n > 0}
    items = [i for i in _account_items(scores, flagged) if i.flagged]
    return MethodResult(items=items, seconds=time.perf_counter() - t0)


# ---------------------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------------------
@dataclass
class DatasetEval:
    dataset_id: str
    seed: int
    precision: str
    truth: list[ScenarioTruth]
    items: list[ReviewItem]
    matches: list[ScenarioTruth | None]
    seconds: float
    n_transfers: int
    partial: bool = False  # the method reported a budget-limited (non-exhaustive) analysis
    quarantined: int = 0  # formations withheld because their evidence failed validation


def evaluate_items(
    ds: GeneratedDataset,
    items: list[ReviewItem],
    seconds: float,
    n_transfers: int,
    budget: int | None = None,
    output: AnalysisOutput | None = None,
) -> DatasetEval:
    ranked = sorted(items, key=lambda i: i.sort_key)
    if budget is not None:  # equal-alert-budget view for score-only baselines
        ranked = [
            ReviewItem(**{**i.__dict__, "flagged": idx < budget})  # type: ignore[arg-type]
            for idx, i in enumerate(ranked)
        ]
    return DatasetEval(
        dataset_id=dataset_id_for(ds),
        seed=ds.seed,
        precision=ds.precision,
        truth=ds.truth,
        items=ranked,
        matches=[match(i, ds.truth) for i in ranked],
        seconds=seconds,
        n_transfers=n_transfers,
        partial=bool(output and output.partial_reasons),
        quarantined=len(output.quarantined) if output else 0,
    )


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


def _f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None or p + r == 0:
        return None if p is None or r is None else 0.0
    return round(2 * p * r / (p + r), 4)


def _mean(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.fmean(vals), 4) if vals else None


def summarize(evals: list[DatasetEval]) -> dict[str, Any]:
    susp_total = legit_total = 0
    tp = fp = 0
    tp_high = fp_high = 0
    surfaced = 0
    flagged_items = relevant_flagged = unmatched_flagged = 0
    fam: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "flagged": 0, "surfaced": 0})
    queue: dict[str, list[float | None]] = defaultdict(list)
    seconds: list[float] = []
    dup_counts: list[int] = []  # flagged alerts per flagged, matched network (1 = no duplicates)
    abstained = abstained_relevant = queued_total = 0
    partial = quarantined = 0
    for ev in evals:
        seconds.append(ev.seconds)
        partial += ev.partial
        quarantined += ev.quarantined
        per_network: dict[str, int] = defaultdict(int)
        flagged_ids: set[str] = set()
        high_ids: set[str] = set()
        surfaced_ids: set[str] = set()
        for item, m in zip(ev.items, ev.matches, strict=True):
            if not item.queued:
                continue
            queued_total += 1
            if item.band == "insufficient_evidence":
                abstained += 1
                abstained_relevant += m is not None and m.label == "suspicious"
            if item.flagged and m is not None:
                per_network[m.scenario_id] += 1
            if item.flagged:
                flagged_items += 1
                if m is None:
                    unmatched_flagged += 1
                elif m.label == "suspicious":
                    relevant_flagged += 1
            if m is not None:
                surfaced_ids.add(m.scenario_id)
                if item.flagged:
                    flagged_ids.add(m.scenario_id)
                if item.band in HIGH_BANDS:
                    high_ids.add(m.scenario_id)
        dup_counts.extend(per_network.values())
        for t in ev.truth:
            f = fam[t.family]
            f["total"] += 1
            f["flagged"] += t.scenario_id in flagged_ids
            f["surfaced"] += t.scenario_id in surfaced_ids
            if t.label == "suspicious":
                susp_total += 1
                tp += t.scenario_id in flagged_ids
                tp_high += t.scenario_id in high_ids
                surfaced += t.scenario_id in surfaced_ids
            else:
                legit_total += 1
                fp += t.scenario_id in flagged_ids
                fp_high += t.scenario_id in high_ids
        # Per-dataset analyst queue (all items in review order, flagged or watch).
        n_susp = sum(1 for t in ev.truth if t.label == "suspicious")
        queued = [(i, m) for i, m in zip(ev.items, ev.matches, strict=True) if i.queued]
        for k in QUEUE_KS:
            top = queued[:k]
            rel = sum(1 for _, m in top if m is not None and m.label == "suspicious")
            reached = {m.scenario_id for _, m in top if m is not None and m.label == "suspicious"}
            queue[f"p_at_{k}"].append(_ratio(rel, len(top)) if top else None)
            # Distinct-network precision: a second alert on an already reached network is not a new find.
            queue[f"distinct_p_at_{k}"].append(_ratio(len(reached), len(top)) if top else None)
            queue[f"recall_at_{k}"].append(_ratio(len(reached), n_susp))
    fn = susp_total - tp
    tn = legit_total - fp
    banded = any(i.band is not None for ev in evals for i in ev.items)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, susp_total)
    sec_sorted = sorted(seconds)
    return {
        "datasets": len(evals),
        "scenario": {
            "suspicious": susp_total,
            "legitimate": legit_total,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "fpr": _ratio(fp, legit_total),
            "fnr": _ratio(fn, susp_total),
            "surfaced_recall": _ratio(surfaced, susp_total),
            # Only meaningful for methods that assign bands (NEXORA); None for account rankings.
            "high_band_recall": _ratio(tp_high, susp_total) if banded else None,
            "high_band_fpr": _ratio(fp_high, legit_total) if banded else None,
        },
        "alerts": {
            "flagged": flagged_items,
            "per_dataset": round(flagged_items / len(evals), 2) if evals else None,
            "precision": _ratio(relevant_flagged, flagged_items),
            "unmatched": unmatched_flagged,
            "per_flagged_network": _mean(float(c) for c in dup_counts),
            "networks_with_duplicates": _ratio(sum(1 for c in dup_counts if c > 1), len(dup_counts)),
        },
        "abstention": {
            "rate": _ratio(abstained, queued_total),
            # Share of abstentions that are planted fraud. Near 1.0 with few legitimate boundary
            # accounts is a sign that the coverage contract leaks the label (audit finding L-01).
            "suspicious_share": _ratio(abstained_relevant, abstained),
        },
        "integrity": {
            "partial_analysis_rate": _ratio(partial, len(evals)),
            "quarantined_formations": quarantined,
        },
        "queue": {name: _mean(vals) for name, vals in sorted(queue.items())},
        "by_family": {k: dict(v) for k, v in sorted(fam.items())},
        "latency_ms": {
            "median": round(statistics.median(sec_sorted) * 1000, 1) if sec_sorted else None,
            "p95": round(sec_sorted[max(0, int(len(sec_sorted) * 0.95) - 1)] * 1000, 1) if sec_sorted else None,
            "max": round(sec_sorted[-1] * 1000, 1) if sec_sorted else None,
        },
    }


def examples(evals: list[DatasetEval], limit: int = 8) -> dict[str, list[dict[str, Any]]]:
    """False-positive (flagged legitimate) and false-negative (missed suspicious) scenarios."""
    fps: list[dict[str, Any]] = []
    fns: list[dict[str, Any]] = []
    for ev in evals:
        best: dict[str, ReviewItem] = {}
        ordered = sorted(zip(ev.items, ev.matches, strict=True), key=lambda im: (not im[0].queued, im[0].sort_key))
        for candidate, m in ordered:
            if m is not None and m.scenario_id not in best:
                best[m.scenario_id] = candidate
        for t in ev.truth:
            item = best.get(t.scenario_id)
            row: dict[str, Any] = {
                "dataset": ev.dataset_id,
                "scenario_id": t.scenario_id,
                "family": t.family,
                "difficulty": t.difficulty,
                "notes": t.notes,
                "kind": item.kind if item else None,
                "band": item.band if item else None,
                "priority": item.priority if item else None,
                "reasons": list(item.reasons) if item else [],
                "explanation": (
                    "no_formation"
                    if item is None
                    else "below_alert_band"
                    if not item.queued
                    else "abstained"
                    if item.band == "insufficient_evidence"
                    else "alerted"
                ),
            }
            if t.label == "legitimate" and item is not None and item.flagged:
                fps.append(row)
            elif t.label == "suspicious" and (item is None or not item.flagged):
                fns.append(row)
    return {"false_positives": fps[:limit], "false_negatives": fns[:limit]}


# ---------------------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------------------
RowsTransform = Callable[[GeneratedDataset, random.Random], tuple[list[dict[str, str]], dict[str, Any]]]


@dataclass
class Experiment:
    name: str
    method: Method
    budget_from: str | None = None  # equal alert budget: flag top-N where N = that method's alert count


@dataclass
class SplitRun:
    split: str
    datasets: list[GeneratedDataset] = field(default_factory=list)
    evals: dict[str, list[DatasetEval]] = field(default_factory=dict)


def load_split(split: str) -> list[GeneratedDataset]:
    if split == "sealed":
        return [generate_sealed(seed) for seed in SPLITS[split]]
    return [generate(SUITE, seed) for seed in SPLITS[split]]


def run_experiments(
    datasets: list[GeneratedDataset],
    experiments: list[Experiment],
    transform: RowsTransform | None = None,
) -> dict[str, list[DatasetEval]]:
    results: dict[str, list[DatasetEval]] = {e.name: [] for e in experiments}
    for ds in datasets:
        rows, contract = (list(ds.rows), dict(ds.coverage_contract))
        if transform is not None:
            rows, contract = transform(ds, random.Random(f"{BENCHMARK_VERSION}|{ds.seed}|perturb"))
        did = dataset_id_for(ds)
        transfers = to_transfers(rows, did)
        flagged_counts: dict[str, int] = {}
        for exp in experiments:
            res = exp.method(transfers, contract, did)
            budget = flagged_counts.get(exp.budget_from) if exp.budget_from else None
            ev = evaluate_items(ds, res.items, res.seconds, len(transfers), budget=budget, output=res.output)
            flagged_counts[exp.name] = sum(1 for i in ev.items if i.flagged and i.queued)
            results[exp.name].append(ev)
    return results


def dataset_manifest(datasets: list[GeneratedDataset]) -> list[dict[str, Any]]:
    return [
        {
            "seed": d.seed,
            "precision": d.precision,
            "rows": len(d.rows),
            "manifest_sha256": d.manifest_sha256,
            "truth_sha256": d.truth_sha256,
            "families": [t.family for t in d.truth],
        }
        for d in datasets
    ]


def split_hash(datasets: list[GeneratedDataset]) -> str:
    return sha256_hex(canonical_json([[d.seed, d.manifest_sha256, d.truth_sha256] for d in datasets]))


# ---------------------------------------------------------------------------------------
# Configuration variants (ablations / shadow policies)
# ---------------------------------------------------------------------------------------
def config_variant(base: AnalysisConfig, edit: Callable[[dict[str, Any], dict[str, Any]], None]) -> AnalysisConfig:
    detectors = copy.deepcopy(base.detectors)
    policy = copy.deepcopy(base.risk_policy)
    edit(detectors, policy)
    return AnalysisConfig(detectors=detectors, risk_policy=policy)


def _v1(det: dict[str, Any], pol: dict[str, Any]) -> None:
    """The configuration shipped before this benchmark existed (detectors-v1 / risk-policy-v1)."""
    det["version"] = "detectors-v1"
    det["funnel"]["detector_version"] = "funnel-v1"
    det["funnel"]["exclude_returning_feeders"] = False
    det["funnel"]["returning_min_ratio"] = 0.1
    det.pop("hypotheses", None)
    pol.pop("hypothesis", None)
    for name in ("fan_out", "cycle", "peer"):
        if name in det:
            det[name]["enabled"] = False
    pol["version"] = "risk-policy-v1"
    pol["caps"].pop("peer_contradicted", None)


def _v2(det: dict[str, Any], pol: dict[str, Any]) -> None:
    """The configuration merged at 4c01a7a (detectors-v2 / risk-policy-v2), the sealed-evaluation baseline.

    Reverses every later change by name, so it stays exact while the candidate evolves:
    funnel-v3's returning ratio, the hypothesis engine (``hypotheses``) and its policy gates.
    """
    det["version"] = "detectors-v2"
    det["funnel"]["detector_version"] = "funnel-v2"
    det["funnel"]["returning_min_ratio"] = 0.1
    det.pop("hypotheses", None)
    pol["version"] = "risk-policy-v2"
    pol.pop("hypothesis", None)


def _no_temporal(det: dict[str, Any], pol: dict[str, Any]) -> None:
    pol["family_weights"]["TEMPORAL"] = 0.0
    for gate in ("temporal_contradicted", "temporal_ambiguous", "temporal_unavailable"):
        pol["caps"][gate] = "critical"
    pol["bands"]["high"]["min_supported_families"] = 1


def _no_peer(det: dict[str, Any], pol: dict[str, Any]) -> None:
    det["peer"]["enabled"] = False
    pol["caps"].pop("peer_contradicted", None)


def _no_new_formations(det: dict[str, Any], pol: dict[str, Any]) -> None:
    det["fan_out"]["enabled"] = False
    det["cycle"]["enabled"] = False


def _no_returning_rule(det: dict[str, Any], pol: dict[str, Any]) -> None:
    det["funnel"]["exclude_returning_feeders"] = False


def _no_coverage_abstention(det: dict[str, Any], pol: dict[str, Any]) -> None:
    pol["abstain_on_subject_limitations"] = []


VARIANTS: dict[str, Callable[[dict[str, Any], dict[str, Any]], None]] = {
    "v1_shipped": _v1,
    "v2_shipped": _v2,
    "minus_temporal": _no_temporal,
    "minus_peer": _no_peer,
    "minus_fan_out_cycle": _no_new_formations,
    "minus_returning_feeder_rule": _no_returning_rule,
    "minus_coverage_abstention": _no_coverage_abstention,
}


# ---------------------------------------------------------------------------------------
# Robustness perturbations (rows -> rows, contract) and threshold sensitivity
# ---------------------------------------------------------------------------------------
def _truth_accounts(ds: GeneratedDataset) -> set[str]:
    return {a for t in ds.truth for a in t.accounts}


def _shuffle(ds: GeneratedDataset, rng: random.Random) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = list(ds.rows)
    rng.shuffle(rows)
    return rows, dict(ds.coverage_contract)


def _duplicates(ds: GeneratedDataset, rng: random.Random) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = list(ds.rows)
    rows += [dict(r) for r in rng.sample(rows, max(1, len(rows) // 20))]
    rng.shuffle(rows)
    return rows, dict(ds.coverage_contract)


def _drop(ds: GeneratedDataset, rng: random.Random) -> tuple[list[dict[str, str]], dict[str, Any]]:
    return [r for r in ds.rows if rng.random() >= 0.10], dict(ds.coverage_contract)


def _jitter(ds: GeneratedDataset, rng: random.Random) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows = []
    for r in ds.rows:
        amount = max(1, int(r["amount_minor"]) * rng.randint(9_900, 10_100) // 10_000)
        rows.append({**r, "amount_minor": str(amount)})
    return rows, dict(ds.coverage_contract)


def _no_timestamps(ds: GeneratedDataset, rng: random.Random) -> tuple[list[dict[str, str]], dict[str, Any]]:
    contract = {**ds.coverage_contract, "time_precision": "day"}
    return [{**r, "occurred_at": ""} for r in ds.rows], contract


def _boundary(ds: GeneratedDataset, rng: random.Random) -> tuple[list[dict[str, str]], dict[str, Any]]:
    accounts = sorted({r["sender_account_id"] for r in ds.rows} | {r["receiver_account_id"] for r in ds.rows})
    extra = rng.sample(accounts, max(1, len(accounts) // 10))
    contract = dict(ds.coverage_contract)
    contract["boundary_account_ids"] = sorted(set(contract.get("boundary_account_ids") or []) | set(extra))
    return list(ds.rows), contract


def _background(factor: int) -> RowsTransform:
    def transform(ds: GeneratedDataset, rng: random.Random) -> tuple[list[dict[str, str]], dict[str, Any]]:
        truth = _truth_accounts(ds)
        everyone = {r["sender_account_id"] for r in ds.rows} | {r["receiver_account_id"] for r in ds.rows}
        background = sorted(everyone - truth)  # planted scenario accounts are never touched
        bg_rows = [r for r in ds.rows if r["sender_account_id"] not in truth and r["receiver_account_id"] not in truth]
        rows = list(ds.rows)
        dates = sorted({r["observed_date"] for r in ds.rows})
        for i in range(len(bg_rows) * (factor - 1)):
            a, b = rng.sample(background, 2)
            rows.append(
                {
                    "source_transaction_id": f"bg{factor}-{i:06d}-{rng.getrandbits(32):08x}",
                    "sender_account_id": a,
                    "receiver_account_id": b,
                    "amount_minor": str(rng.randrange(1_000, 120_000) * 100 + rng.randrange(100)),
                    "currency": "KZT",
                    "observed_date": rng.choice(dates),
                    "occurred_at": "",
                    "status": "posted",
                }
            )
        if ds.precision == "timestamp":  # keep the dataset's precision uniform
            rows = [{**r, "occurred_at": ""} for r in rows]
        return rows, {**ds.coverage_contract, "time_precision": "day"}

    return transform


PERTURBATIONS: dict[str, tuple[RowsTransform, str]] = {
    "shuffled_rows": (_shuffle, "row order shuffled (out-of-order arrival)"),
    "duplicate_rows_5pct": (_duplicates, "5% of rows re-sent as exact duplicates"),
    "missing_rows_10pct": (_drop, "10% of rows missing at random"),
    "amount_jitter_1pct": (_jitter, "every amount perturbed by up to +/-1%"),
    "timestamps_removed": (_no_timestamps, "intraday timestamps removed (day precision only)"),
    "boundary_10pct": (_boundary, "10% of accounts declared at the collection boundary"),
    "background_x2": (_background(2), "twice the unlabelled background volume"),
    "background_x4": (_background(4), "four times the unlabelled background volume"),
}


def _set(path: tuple[str, ...], value: Any) -> Callable[[dict[str, Any], dict[str, Any]], None]:
    def edit(det: dict[str, Any], pol: dict[str, Any]) -> None:
        target = det
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return edit


SENSITIVITY: dict[str, Callable[[dict[str, Any], dict[str, Any]], None]] = {
    "funnel.min_feeder_share=0.4": _set(("funnel", "min_feeder_share"), 0.4),
    "funnel.min_feeder_share=0.6": _set(("funnel", "min_feeder_share"), 0.6),
    "temporal.max_hop_lag_days=5": _set(("temporal", "max_hop_lag_days"), 5),
    "temporal.max_hop_lag_days=10": _set(("temporal", "max_hop_lag_days"), 10),
    "fan_out.min_recipients=4": _set(("fan_out", "min_recipients"), 4),
    "fan_out.min_recipients=6": _set(("fan_out", "min_recipients"), 6),
    "peer.fence_iqr_multiplier=1.0": _set(("peer", "fence_iqr_multiplier"), 1.0),
    "peer.fence_iqr_multiplier=2.0": _set(("peer", "fence_iqr_multiplier"), 2.0),
}


def identical_items(a: list[DatasetEval], b: list[DatasetEval]) -> bool:
    def key(evals: list[DatasetEval]) -> list[list[tuple[str, str | None, int | None]]]:
        return [sorted((i.item_id, i.band, i.priority) for i in ev.items) for ev in evals]

    return key(a) == key(b)
