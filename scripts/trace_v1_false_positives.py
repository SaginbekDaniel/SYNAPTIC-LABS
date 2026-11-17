"""Trace the two documented v1 false positives from score to transactions.

Usage: ``uv run python scripts/trace_v1_false_positives.py [--config-dir configs/v1]``

Reproduces docs/FRAUD_FAILURE_ANALYSIS.md on the ``demo-v1`` suite, seed 2026, day precision.
Ground truth is used only to *label* the printed formations, never as detector input.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from nexora.analytics.config import load_config
from nexora.analytics.pipeline import AnalysisOutput, run_analysis
from nexora.analytics.structural.chain import _is_intermediary
from nexora.domain.ids import canonical_json, sha256_hex
from nexora.domain.transfers import ObservedTransfer
from nexora.evaluation.generator import GeneratedDataset, generate


def load(suite: str, seed: int) -> tuple[GeneratedDataset, list[ObservedTransfer]]:
    ds = generate(suite, seed)
    transfers = [
        ObservedTransfer(
            transaction_id=r["source_transaction_id"],
            source_transaction_id=r["source_transaction_id"],
            sender=r["sender_account_id"],
            receiver=r["receiver_account_id"],
            amount_minor=int(r["amount_minor"]),
            currency=r["currency"],
            observed_date=date.fromisoformat(r["observed_date"]),
            occurred_at=None,
            precision="day",
            status=r["status"],  # type: ignore[arg-type]
        )
        for r in ds.rows
    ]
    return ds, transfers


def assessments_fingerprint(out: AnalysisOutput) -> str:
    return sha256_hex(
        canonical_json(
            sorted([a.id, a.band, a.priority, [r.as_dict() for r in a.reason_codes]] for a in out.assessments)
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", default="configs/v1")
    args = parser.parse_args()
    ds, transfers = load("demo-v1", 2026)
    cfg = load_config(Path(args.config_dir))
    out = run_analysis(dataset_id="demo", transfers=transfers, contract=ds.coverage_contract, config=cfg)
    print("assessments:", len(out.assessments), "fingerprint:", assessments_fingerprint(out))

    truth = {s.family: s for s in ds.truth}
    formations = {f.id: f for f in out.formations}
    signals = {s.id: s for s in out.signals}
    inflows: dict[str, list[ObservedTransfer]] = defaultdict(list)
    outflows: dict[str, list[ObservedTransfer]] = defaultdict(list)
    for t in transfers:
        inflows[t.receiver].append(t)
        outflows[t.sender].append(t)
    cg = out.snapshot.by_currency["KZT"]

    for family in ("N2_merchant_settlement", "S1_collection_funnel"):
        accounts = set(truth[family].accounts)
        a = next(
            a
            for a in out.assessments
            if formations[a.formation_id].kind == "funnel" and formations[a.formation_id].subject_account_id in accounts
        )
        f = formations[a.formation_id]
        c = f.subject_account_id
        per_feeder = Counter(t.sender for t in inflows[c] if t.sender in f.entry_ids)
        repeat = sum(1 for k in f.entry_ids if len({t.observed_date for t in inflows[c] if t.sender == k}) >= 2)
        print(f"\n== {family}: priority={a.priority} band={a.band}")
        for sid in a.signal_ids:
            print(f"   signal {signals[sid].family:<9} {signals[sid].status:<18} strength={signals[sid].strength}")
        print(f"   in/out transfers {len(inflows[c])}/{len(outflows[c])}; qualifying feeders {len(f.entry_ids)}")
        print(f"   transfers per feeder {sorted(per_feeder.values())}; feeders on >=2 days {repeat}")
        print(f"   inflow days {sorted({t.observed_date.day for t in inflows[c]})}")
        print(f"   outflow days {sorted({t.observed_date.day for t in outflows[c]})}")
        print(f"   payouts per recipient {sorted(Counter(t.receiver for t in outflows[c]).values())}")

    scenario_accounts = {acc for s in ds.truth for acc in s.accounts}
    for a in out.assessments:
        f = formations[a.formation_id]
        if f.kind != "chain" or a.band != "high" or set(f.member_ids) & scenario_accounts:
            continue
        p = f.member_ids
        print(f"\n== background chain priority={a.priority} band={a.band}")
        for i in range(len(p) - 1):
            e = cg.edges[(p[i], p[i + 1])]
            print(
                f"   hop{i} {e.amount_minor / 100:.2f} KZT n_tx={e.n_transactions}"
                f" days {e.first_date.day}..{e.last_date.day}"
            )
        for i, n in enumerate(p[1:-1], start=1):
            m = cg.metrics[n]
            pin = cg.edges[(p[i - 1], n)].amount_minor
            pout = cg.edges[(n, p[i + 1])].amount_minor
            print(
                f"   intermediary deg {m.in_degree}/{m.out_degree} path share in {pin / m.incoming_minor:.2f}"
                f" out {pout / m.outgoing_minor:.2f}"
            )
    chain_cfg = cfg.detectors["chain"]
    from fractions import Fraction

    background = [n for n in cg.graph.nodes if n not in scenario_accounts]
    qualifying = [
        n
        for n in background
        if _is_intermediary(
            cg, n, int(chain_cfg["intermediary_max_degree"]), Fraction(str(chain_cfg["pass_through_min_ratio"]))
        )
    ]
    chains = [f for f in out.formations if f.kind == "chain"]
    print(f"\nbackground accounts {len(background)}, qualifying as intermediaries {len(qualifying)}")
    print(
        f"chain candidates {len(chains)}, touching no scenario "
        f"{sum(1 for f in chains if not set(f.member_ids) & scenario_accounts)}"
    )


if __name__ == "__main__":
    main()
