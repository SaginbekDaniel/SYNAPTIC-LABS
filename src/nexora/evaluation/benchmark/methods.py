"""Detection methods compared by the benchmark.

Every method sees only ``NetworkInput`` (rows + coverage contract) and returns ranked
``Prediction`` objects. Rows go through the production ingest validation (``prepare_batch``)
and the production pure pipeline, exactly as the worker would run them — minus the database.

Account-level baselines (volume, centrality, static rules) have one operating threshold each,
fitted on the **development split only** (the only place labels are visible to a method), by
maximising scenario-level F1. That gives baselines their best dev operating point.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from nexora.analytics import risk as risk_engine
from nexora.analytics.config import CONFIG_DIR, AnalysisConfig, load_config
from nexora.analytics.pipeline import AnalysisOutput, run_analysis
from nexora.domain.analysis import BAND_ORDER
from nexora.domain.ids import transaction_uuid
from nexora.domain.transfers import ObservedTransfer
from nexora.evaluation.benchmark.suite import Network, NetworkInput
from nexora.ingest.validation import ImportReport, prepare_batch

Status = Literal["raised", "abstained", "below"]


@dataclass(frozen=True)
class Prediction:
    pred_id: str
    kind: str
    status: Status
    score: float | None  # review-order key: higher is reviewed first; None = not rankable
    band: str | None
    accounts: tuple[str, ...]
    source_tx_ids: tuple[str, ...]
    reasons: tuple[str, ...] = ()


@dataclass
class MethodResult:
    predictions: list[Prediction]
    latency_ms: float
    n_transactions: int
    partial_reasons: list[str] = field(default_factory=list)
    import_report: dict[str, Any] = field(default_factory=dict)


class Method(Protocol):
    name: str
    group: str
    description: str

    def fit(self, dev: Sequence[Network]) -> None: ...

    def run(self, inp: NetworkInput) -> MethodResult: ...

    def describe(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------------------
# shared input conversion
# ---------------------------------------------------------------------------------------


def to_transfers(inp: NetworkInput) -> tuple[list[ObservedTransfer], dict[str, str], ImportReport]:
    records, report = prepare_batch(list(enumerate(inp.rows, start=1)), source_id="synthetic", is_synthetic=True)
    transfers: list[ObservedTransfer] = []
    source_of: dict[str, str] = {}
    for r in records:
        tid = transaction_uuid(inp.network_id, r.source_id, r.source_transaction_id)
        source_of[tid] = r.source_transaction_id
        transfers.append(
            ObservedTransfer(
                transaction_id=tid,
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
        )
    return transfers, source_of, report


# ---------------------------------------------------------------------------------------
# NEXORA engine variants
# ---------------------------------------------------------------------------------------

ConfigTransform = Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]


def _review_score(band: str, priority: int | None) -> float | None:
    if band == "insufficient_evidence" or priority is None:
        return None
    return BAND_ORDER.index(band) * 1000 + priority


@dataclass
class NexoraMethod:
    """The production pipeline under a given (possibly ablated) configuration."""

    name: str
    description: str
    config: AnalysisConfig
    group: str = "nexora"

    def fit(self, dev: Sequence[Network]) -> None:  # the engine is not fitted to labels
        return None

    def analyse(self, inp: NetworkInput) -> tuple[AnalysisOutput, dict[str, str], ImportReport, float]:
        t0 = time.perf_counter()
        transfers, source_of, report = to_transfers(inp)
        out = run_analysis(
            dataset_id=inp.network_id, transfers=transfers, contract=inp.coverage_contract, config=self.config
        )
        return out, source_of, report, (time.perf_counter() - t0) * 1000

    def run(self, inp: NetworkInput) -> MethodResult:
        out, source_of, report, ms = self.analyse(inp)
        return MethodResult(
            predictions=predictions_from_output(out, source_of, self.config.risk_policy),
            latency_ms=ms,
            n_transactions=out.snapshot.eligible_count,
            partial_reasons=list(out.partial_reasons),
            import_report={"accepted": report.accepted, "duplicated_identical": report.duplicated_identical},
        )

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group,
            "description": self.description,
            "detectors_version": self.config.detectors.get("version"),
            "policy_version": self.config.policy_version,
            "config_sha256": self.config.config_sha256,
        }


def predictions_from_output(out: AnalysisOutput, source_of: dict[str, str], policy: dict[str, Any]) -> list[Prediction]:
    formations = {f.id: f for f in out.formations}
    preds: list[Prediction] = []
    for a in out.assessments:
        f = formations[a.formation_id]
        if a.band == "insufficient_evidence":
            status: Status = "abstained"
        elif risk_engine.opens_alert(a.band, policy):
            status = "raised"
        else:
            status = "below"
        preds.append(
            Prediction(
                pred_id=a.formation_id,
                kind=f.kind,
                status=status,
                score=_review_score(a.band, a.priority),
                band=a.band,
                accounts=tuple(f.member_ids),
                source_tx_ids=tuple(sorted(source_of[t] for t in f.transaction_ids)),
                reasons=tuple(r.code for r in a.reason_codes),
            )
        )
    return preds


def load_engine(version: Literal["v1", "v2"]) -> AnalysisConfig:
    return load_config(CONFIG_DIR / "v1") if version == "v1" else load_config(CONFIG_DIR)


def variant(base: AnalysisConfig, transform: ConfigTransform) -> AnalysisConfig:
    import copy

    detectors, policy = transform(copy.deepcopy(base.detectors), copy.deepcopy(base.risk_policy))
    return AnalysisConfig(detectors=detectors, risk_policy=policy)


def structural_only(detectors: dict[str, Any], policy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Every structural formation is an alert, ranked by structural priority.

    Temporal signals are ignored, chronology caps and abstention gates are removed, and the
    medium band starts at priority 0 — otherwise the un-renormalised priority (max 35 from
    STRUCTURE alone) would silently suppress most structural detections and handicap this
    baseline.
    """
    policy["ignore_families"] = ["TEMPORAL"]
    policy["caps"] = {k: "critical" for k in policy["caps"]}
    policy["bands"]["high"]["min_supported_families"] = 1
    policy["bands"]["medium"]["min_priority"] = 0
    policy["bands"]["low"]["min_priority"] = 0
    policy["abstain_on_subject_limitations"] = []
    return detectors, policy


# ---------------------------------------------------------------------------------------
# account-level baselines
# ---------------------------------------------------------------------------------------


@dataclass
class AccountStats:
    incoming: int = 0
    outgoing: int = 0
    senders: set[str] = field(default_factory=set)
    receivers: set[str] = field(default_factory=set)
    max_single: int = 0
    in_days: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))
    out_days: dict[str, list[Any]] = field(default_factory=lambda: defaultdict(list))


def account_stats(transfers: list[ObservedTransfer]) -> dict[str, AccountStats]:
    stats: dict[str, AccountStats] = defaultdict(AccountStats)
    for t in transfers:
        if not t.eligible or t.is_self_transfer:
            continue
        s, r = stats[t.sender], stats[t.receiver]
        s.outgoing += t.amount_minor
        r.incoming += t.amount_minor
        s.receivers.add(t.receiver)
        r.senders.add(t.sender)
        s.max_single = max(s.max_single, t.amount_minor)
        r.max_single = max(r.max_single, t.amount_minor)
        s.out_days[t.receiver].append(t.observed_date)
        r.in_days[t.sender].append(t.observed_date)
    return stats


def _max_distinct_in_window(by_counterparty: dict[str, list[Any]], days: int) -> int:
    events = sorted((d, c) for c, ds in by_counterparty.items() for d in ds)
    best = 0
    for i, (d0, _) in enumerate(events):
        window = {c for d, c in events[i:] if d - d0 <= timedelta(days=days - 1)}
        best = max(best, len(window))
    return best


def pagerank(transfers: list[ObservedTransfer], damping: float = 0.85, iterations: int = 60) -> dict[str, float]:
    """Amount-weighted PageRank by power iteration (no SciPy dependency). Ranking-only floats."""
    weights: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    nodes: set[str] = set()
    for t in transfers:
        if t.eligible and not t.is_self_transfer:
            weights[t.sender][t.receiver] += t.amount_minor
            nodes.update((t.sender, t.receiver))
    if not nodes:
        return {}
    order = sorted(nodes)
    n = len(order)
    rank = dict.fromkeys(order, 1.0 / n)
    out_total = {u: sum(vs.values()) for u, vs in weights.items()}
    for _ in range(iterations):
        dangling = sum(rank[u] for u in order if u not in out_total)
        nxt = dict.fromkeys(order, (1 - damping) / n + damping * dangling / n)
        for u, vs in weights.items():
            for v, w in vs.items():
                nxt[v] += damping * rank[u] * w / out_total[u]
        rank = nxt
    return {u: r * n for u, r in rank.items()}  # relative to uniform, comparable across networks


AccountScorer = Callable[[list[ObservedTransfer], dict[str, AccountStats], dict[str, Any]], dict[str, float]]


@dataclass
class AccountBaseline:
    name: str
    description: str
    scorer: AccountScorer
    params: dict[str, Any] = field(default_factory=dict)
    threshold: float | None = None
    group: str = "baseline"
    fit_grid: dict[str, list[Any]] = field(default_factory=dict)

    def scores(self, inp: NetworkInput) -> tuple[dict[str, float], int, float]:
        t0 = time.perf_counter()
        transfers, _, _ = to_transfers(inp)
        scores = self.scorer(transfers, account_stats(transfers), self.params)
        return scores, sum(1 for t in transfers if t.eligible), (time.perf_counter() - t0) * 1000

    def fit(self, dev: Sequence[Network]) -> None:
        from nexora.evaluation.benchmark.metrics import best_f1_threshold

        candidates = [dict(zip(self.fit_grid, combo, strict=True)) for combo in _product(self.fit_grid)] or [{}]
        best: tuple[float, float, dict[str, Any]] | None = None
        for params in candidates:
            self.params.update(params)
            scenario_scores = []
            for net in dev:
                scores, _, _ = self.scores(net.input)
                planted = [scores[a] for a in net.truth.accounts if a in scores]
                scenario_scores.append((net.truth.label == "suspicious", max(planted) if planted else None))
            f1, tau = best_f1_threshold(scenario_scores)
            if best is None or f1 > best[0]:
                best = (f1, tau, dict(params))
        assert best is not None
        self.params.update(best[2])
        self.threshold = best[1]

    def run(self, inp: NetworkInput) -> MethodResult:
        if self.threshold is None:
            raise RuntimeError(f"{self.name} must be fitted on the development split first")
        scores, n_tx, ms = self.scores(inp)
        preds = [
            Prediction(
                pred_id=acc,
                kind="account",
                status="raised" if score >= self.threshold else "below",
                score=score,
                band=None,
                accounts=(acc,),
                source_tx_ids=(),
            )
            for acc, score in sorted(scores.items())
            if score > 0
        ]
        return MethodResult(predictions=preds, latency_ms=ms, n_transactions=n_tx)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group,
            "description": self.description,
            "params": {k: v for k, v in self.params.items()},
            "threshold_fitted_on_dev": self.threshold,
        }


def _product(grid: dict[str, list[Any]]) -> list[tuple[Any, ...]]:
    import itertools

    return list(itertools.product(*grid.values())) if grid else []


def volume_scorer(_: list[ObservedTransfer], stats: dict[str, AccountStats], __: dict[str, Any]) -> dict[str, float]:
    return {a: float(s.incoming + s.outgoing) for a, s in stats.items()}


def centrality_scorer(
    transfers: list[ObservedTransfer], _: dict[str, AccountStats], __: dict[str, Any]
) -> dict[str, float]:
    return pagerank(transfers)


def static_rules_scorer(
    _: list[ObservedTransfer], stats: dict[str, AccountStats], params: dict[str, Any]
) -> dict[str, float]:
    """Classic threshold rules; score = number of rules fired (0-3).

    R1 any single transfer >= ``large_minor``; R2 >= ``fan`` distinct senders within 7 days;
    R3 >= ``fan`` distinct receivers within 7 days.
    """
    large, fan = int(params["large_minor"]), int(params["fan"])
    out: dict[str, float] = {}
    for a, s in stats.items():
        fired = int(s.max_single >= large)
        fired += int(_max_distinct_in_window(s.in_days, 7) >= fan)
        fired += int(_max_distinct_in_window(s.out_days, 7) >= fan)
        out[a] = float(fired)
    return out


def default_methods(*, include_v2: bool = True) -> list[Method]:
    v1 = load_engine("v1")
    methods: list[Method] = [
        AccountBaseline("B0_volume", "Accounts ranked by total observed in+out volume", volume_scorer),
        AccountBaseline("B1_centrality", "Amount-weighted PageRank (relative to uniform)", centrality_scorer),
        AccountBaseline(
            "B2_static_rules",
            "Large single transfer, 7-day fan-in or fan-out rules",
            static_rules_scorer,
            params={"large_minor": 100_000_000, "fan": 5},
            fit_grid={"large_minor": [50_000_000, 100_000_000, 200_000_000, 500_000_000], "fan": [4, 5, 7, 10]},
        ),
        NexoraMethod("B3_v1_structural_only", "v1 formations, structure credited only", variant(v1, structural_only)),
        NexoraMethod("B4_v1_structural_temporal", "v1 engine as shipped: structure + temporal + coverage", v1),
    ]
    if include_v2 and (Path(CONFIG_DIR) / "detectors.yaml").exists():
        v2 = load_engine("v2")
        if v2.config_sha256 != v1.config_sha256:
            methods.append(NexoraMethod("B5_v2_full", "v2 engine: all detectors, context, coverage", v2))
    return methods
