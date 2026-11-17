"""Ablation, robustness and scale experiments on one frozen split.

Every experiment re-runs a method on the same networks and reports the full metric summary plus
*which* scenario outcomes changed relative to the unmodified reference run, grouped as
``family: before->after`` transitions, so a metric shift can be traced to concrete networks.

Perturbations transform only detector input (rows / contract). Ground truth is used solely to
score; the "larger benign volume" perturbation adds a fresh unlabelled population.
"""

from __future__ import annotations

import copy
import random
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from nexora.analytics.config import AnalysisConfig
from nexora.evaluation.benchmark import scenarios as sc
from nexora.evaluation.benchmark.methods import NexoraMethod, load_engine, variant
from nexora.evaluation.benchmark.metrics import NetworkOutcome
from nexora.evaluation.benchmark.suite import Network, NetworkInput, Suite

Transform = Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]
Perturbation = Callable[[NetworkInput], NetworkInput]


# -- ablations (configuration transforms of the full v2 engine) -----------------------------


def _no_temporal(d: dict[str, Any], p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    p["ignore_families"] = ["TEMPORAL"]
    p["caps"] = {k: "critical" for k in p["caps"]}
    return d, p


def _no_attribution(d: dict[str, Any], p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    d["temporal"].pop("attribution", None)
    return d, p


def _no_context(d: dict[str, Any], p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    d.pop("context", None)
    return d, p


def _no_coverage(d: dict[str, Any], p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    p["abstain_on_subject_limitations"] = []
    return d, p


def _disable(*names: str) -> Transform:
    def t(d: dict[str, Any], p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        for n in names:
            d[n]["enabled"] = False
        return d, p

    return t


def _dedication_off(d: dict[str, Any], p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    for n in ("funnel", "fanout"):
        d[n].pop("strength_model", None)
    return d, p


ABLATIONS: dict[str, tuple[str, Transform]] = {
    "no_temporal_corroboration": ("TEMPORAL family not credited, chronology caps removed", _no_temporal),
    "no_fungibility_attribution": ("max-flow bound only (v1 temporal attribution)", _no_attribution),
    "no_benign_context": ("counter-evidence indicators not computed", _no_context),
    "no_coverage_safeguards": ("no abstention on boundary-limited subjects", _no_coverage),
    "no_dedication_strength": ("v1 count-based structural strength", _dedication_off),
    "no_funnel_detector": ("funnel formations disabled", _disable("funnel")),
    "no_chain_detector": ("chain formations disabled", _disable("chain")),
    "no_fanout_detector": ("fan-out formations disabled", _disable("fanout")),
    "no_cycle_detector": ("cycle formations disabled", _disable("cycle")),
}


def _scaled(factor_num: int, factor_den: int) -> Transform:
    """Scale every share/fraction/amount threshold by num/den (shares capped at 1)."""

    def scale_share(v: Any) -> str:
        from fractions import Fraction

        return str(min(Fraction(1), Fraction(str(v)) * factor_num / factor_den))

    def scale_minor(v: Any) -> str:
        return str(int(v) * factor_num // factor_den)

    def t(d: dict[str, Any], p: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        d["funnel"]["min_feeder_share"] = scale_share(d["funnel"]["min_feeder_share"])
        d["funnel"]["min_incoming_minor"] = scale_minor(d["funnel"]["min_incoming_minor"])
        d["fanout"]["min_recipient_share"] = scale_share(d["fanout"]["min_recipient_share"])
        d["fanout"]["min_outgoing_minor"] = scale_minor(d["fanout"]["min_outgoing_minor"])
        d["chain"]["min_edge_minor"] = scale_minor(d["chain"]["min_edge_minor"])
        d["cycle"]["min_edge_minor"] = scale_minor(d["cycle"]["min_edge_minor"])
        d["temporal"]["min_compatible_fraction"] = scale_share(d["temporal"]["min_compatible_fraction"])
        d["temporal"]["max_hop_lag_days"] = max(
            1, round(int(d["temporal"]["max_hop_lag_days"]) * factor_num / factor_den)
        )
        return d, p

    return t


THRESHOLD_SENSITIVITY: dict[str, tuple[str, Transform]] = {
    "thresholds_minus_20pct": ("share, fraction, amount and lag thresholds x0.8", _scaled(4, 5)),
    "thresholds_plus_20pct": ("share, fraction, amount and lag thresholds x1.2", _scaled(6, 5)),
}


# -- input perturbations -------------------------------------------------------------------


def _rng(inp: NetworkInput, name: str) -> random.Random:
    return random.Random(f"perturb|{name}|{inp.network_id}")


def drop_transactions(share_pct: int) -> Perturbation:
    def p(inp: NetworkInput) -> NetworkInput:
        rng = _rng(inp, f"drop{share_pct}")
        rows = tuple(r for r in inp.rows if rng.randrange(100) >= share_pct)
        return replace(inp, rows=rows)

    return p


def strip_timestamps(inp: NetworkInput) -> NetworkInput:
    rows = tuple({**r, "occurred_at": ""} for r in inp.rows)
    return replace(inp, rows=rows, coverage_contract={**inp.coverage_contract, "time_precision": "day"})


def exact_duplicates(inp: NetworkInput) -> NetworkInput:
    rng = _rng(inp, "dup")
    extra = tuple(dict(r) for r in inp.rows if rng.randrange(100) < 10)
    return replace(inp, rows=inp.rows + extra)


def double_posting(inp: NetworkInput) -> NetworkInput:
    """5 % of transfers re-sent under a new source id (a duplicate ingestion cannot recognise)."""
    rng = _rng(inp, "double")
    extra = tuple(
        {**r, "source_transaction_id": r["source_transaction_id"] + "-dup"} for r in inp.rows if rng.randrange(100) < 5
    )
    return replace(inp, rows=inp.rows + extra)


def reverse_order(inp: NetworkInput) -> NetworkInput:
    return replace(inp, rows=tuple(reversed(inp.rows)))


def more_benign_volume(inp: NetworkInput) -> NetworkInput:
    """Triple the activity: a fresh unlabelled population, 20 % of it trading with existing accounts."""
    rng = _rng(inp, "volume")
    start, end = inp.window
    net = sc.Net(rng=rng, start=start, days=(end - start).days + 1, precision=inp.coverage_contract["time_precision"])
    net.recording = False
    net.used_tx = {r["source_transaction_id"] for r in inp.rows}
    existing = sorted({r["sender_account_id"] for r in inp.rows} | {r["receiver_account_id"] for r in inp.rows})
    net.used_accounts = set(existing)
    bg = sc.background(net, n_accounts=max(20, len(existing)), n_transfers=2 * len(inp.rows))
    for _ in range(len(inp.rows) // 5):
        a, b = rng.choice(bg), rng.choice(existing)
        sender, receiver = (a, b) if rng.random() < 0.5 else (b, a)
        net.tx(sender, receiver, net.kzt(500, 150_000), rng.randrange(net.days))
    return replace(inp, rows=inp.rows + tuple(net.rows))


def window_prefix(pct: int) -> Perturbation:
    def p(inp: NetworkInput) -> NetworkInput:
        start, end = inp.window
        last = start + timedelta(days=((end - start).days + 1) * pct // 100 - 1)
        rows = tuple(r for r in inp.rows if date.fromisoformat(r["observed_date"]) <= last)
        return replace(inp, rows=rows, window=(start, last))

    return p


def window_suffix(pct: int) -> Perturbation:
    def p(inp: NetworkInput) -> NetworkInput:
        start, end = inp.window
        first = end - timedelta(days=((end - start).days + 1) * pct // 100 - 1)
        rows = tuple(r for r in inp.rows if date.fromisoformat(r["observed_date"]) >= first)
        return replace(inp, rows=rows, window=(first, end))

    return p


PERTURBATIONS: dict[str, tuple[str, Perturbation]] = {
    "missing_edges_10pct": ("10 % of transactions removed at random", drop_transactions(10)),
    "missing_edges_25pct": ("25 % of transactions removed at random", drop_transactions(25)),
    "missing_timestamps": ("intraday timestamps removed: day precision only", strip_timestamps),
    "duplicate_rows": ("10 % of rows re-sent with the same source id", exact_duplicates),
    "double_posting": ("5 % of transfers re-sent under a new source id", double_posting),
    "out_of_order_ingestion": ("rows supplied in reverse order", reverse_order),
    "larger_benign_volume": ("3x activity from an added unlabelled population", more_benign_volume),
    "partial_window_first_60pct": ("only the first 60 % of the observation window", window_prefix(60)),
    "partial_window_last_60pct": ("only the last 60 % of the observation window", window_suffix(60)),
}


# -- execution -------------------------------------------------------------------------------


BandMap = dict[tuple[str, str, tuple[str, ...]], str]


def _transitions(ref: Sequence[NetworkOutcome], new: Sequence[NetworkOutcome]) -> tuple[int, dict[str, int]]:
    before = {o.network_id: o for o in ref}
    moves: Counter[str] = Counter()
    for o in new:
        b = before[o.network_id]
        if b.outcome != o.outcome:
            moves[f"{o.family}: {b.outcome}->{o.outcome}"] += 1
    return sum(moves.values()), dict(sorted(moves.items()))


def _band_moves(ref: BandMap, new: BandMap) -> dict[str, int]:
    """Assessment band changes for formations present in both runs (keyed by content, not id:
    formation ids are content-derived from the input manifest, so any perturbation changes them)."""
    moves: Counter[str] = Counter(f"{ref[k]}->{new[k]}" for k in ref.keys() & new.keys() if ref[k] != new[k])
    moves["formations_only_in_reference"] = len(ref.keys() - new.keys())
    moves["formations_only_in_experiment"] = len(new.keys() - ref.keys())
    return dict(sorted(moves.items()))


def _perturbed(nets: Sequence[Network], fn: Perturbation) -> list[Network]:
    return [replace(n, input=fn(n.input)) for n in nets]


def _summary(method: NexoraMethod, nets: Sequence[Network]) -> tuple[dict[str, Any], list[NetworkOutcome], BandMap]:
    from nexora.evaluation.benchmark.metrics import score_network, summarise

    outcomes: list[NetworkOutcome] = []
    ranked: list[tuple[float, str, Any, Any]] = []
    bands: BandMap = {}
    for net in nets:
        result = method.run(net.input)
        accounts = {r["sender_account_id"] for r in net.input.rows} | {r["receiver_account_id"] for r in net.input.rows}
        outcomes.append(score_network(net.split, net.truth, result, accounts))
        for p in result.predictions:
            bands[(net.truth.network_id, p.kind, p.accounts)] = p.band or p.status
            if p.status == "raised" and p.score is not None:
                ranked.append((p.score, net.truth.network_id, p, net.truth))
    return summarise(outcomes, ranked), outcomes, bands


def scale_test(nets: Sequence[Network], config: AnalysisConfig, name: str) -> dict[str, Any]:
    """All networks of the split merged into one dataset and analysed once (cold, single process)."""
    rows: list[dict[str, str]] = []
    boundary: set[str] = set()
    for i, n in enumerate(nets):
        rows.extend({**r, "source_transaction_id": f"{i:04d}-{r['source_transaction_id']}"} for r in n.input.rows)
        boundary.update(n.input.coverage_contract["boundary_account_ids"])
    start = min(n.input.window[0] for n in nets)
    end = max(n.input.window[1] for n in nets)
    contract = {**nets[0].input.coverage_contract, "boundary_account_ids": sorted(boundary), "time_precision": "mixed"}
    merged = NetworkInput("scale", tuple(rows), contract, (start, end))
    method = NexoraMethod(name, "", config)
    t0 = time.perf_counter()
    out, _, _, _ = method.analyse(merged)
    elapsed = time.perf_counter() - t0
    return {
        "method": name,
        "networks_merged": len(nets),
        "transactions": out.snapshot.eligible_count,
        "accounts": out.snapshot.nodes_count,
        "edges": out.snapshot.edges_count,
        "formations": len(out.formations),
        "partial_reasons": out.partial_reasons,
        "wall_seconds": round(elapsed, 2),
        "note": "single cold run including ingest validation; machine-dependent",
    }


def run_experiments(suite: Suite, *, split: str) -> dict[str, Any]:
    nets = suite.split(split)
    v2 = load_engine("v2")
    full = NexoraMethod("B5_v2_full", "", v2)
    ref_metrics, ref, ref_bands = _summary(full, nets)
    ablations: list[dict[str, Any]] = [
        {
            "name": "full_v2_reference",
            "description": "unmodified v2 engine",
            "split": split,
            "metrics": ref_metrics,
            "changed": 0,
        }
    ]
    for name, (desc, transform) in {**ABLATIONS, **THRESHOLD_SENSITIVITY}.items():
        cfg = variant(v2, transform)
        metrics, outcomes, bands = _summary(NexoraMethod(name, desc, cfg), nets)
        changed, moves = _transitions(ref, outcomes)
        ablations.append(
            {
                "name": name,
                "description": desc,
                "split": split,
                "config_sha256": cfg.config_sha256,
                "metrics": metrics,
                "changed": changed,
                "transitions": moves,
                "band_changes": _band_moves(ref_bands, bands),
            }
        )
    robustness: list[dict[str, Any]] = []
    v1 = NexoraMethod("B4_v1_structural_temporal", "", load_engine("v1"))
    _, ref_v1, ref_v1_bands = _summary(v1, nets)
    for name, (desc, fn) in PERTURBATIONS.items():
        pnets = _perturbed(nets, fn)
        for method, reference, ref_b in ((full, ref, ref_bands), (v1, ref_v1, ref_v1_bands)):
            metrics, outcomes, bands = _summary(method, pnets)
            changed, moves = _transitions(reference, outcomes)
            robustness.append(
                {
                    "name": f"{name} [{method.name}]",
                    "perturbation": name,
                    "method": method.name,
                    "description": desc,
                    "split": split,
                    "metrics": metrics,
                    "changed": changed,
                    "transitions": moves,
                    "band_changes": _band_moves(ref_b, bands),
                }
            )
    scale = [scale_test(nets, copy.deepcopy(v2), "B5_v2_full"), scale_test(nets, load_engine("v1"), "B4_v1")]
    return {"ablations": ablations, "robustness": robustness, "scale": scale}
