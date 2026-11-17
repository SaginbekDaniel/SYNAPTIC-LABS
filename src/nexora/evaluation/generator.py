"""Deterministic synthetic scenario generator (spec §18).

Output rows are canonical *source* records only. Ground-truth labels are returned in a
separate structure and are never written into transaction rows or the runtime database
(ADR-009). Account and transaction identifiers are random and carry no role prefix, so
string patterns cannot leak the scenario class. Some account IDs exceed 2^53-1 on
purpose to exercise exact-string handling end to end.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from nexora.domain.ids import canonical_json, sha256_hex

GENERATOR_VERSION = "synthetic-gen-v1"
Precision = Literal["day", "timestamp"]
Label = Literal["suspicious", "legitimate"]
Difficulty = Literal["easy", "medium", "hard", "adversarial"]


@dataclass
class ScenarioTruth:
    scenario_id: str
    family: str
    label: Label
    difficulty: Difficulty
    accounts: list[str]
    source_transaction_ids: list[str]
    notes: str


@dataclass
class GeneratedDataset:
    suite: str
    seed: int
    precision: Precision
    rows: list[dict[str, str]]
    coverage_contract: dict[str, Any]
    truth: list[ScenarioTruth]
    window: tuple[date, date]

    @property
    def manifest_sha256(self) -> str:
        return sha256_hex(canonical_json(sorted(canonical_json(r) for r in self.rows)))

    @property
    def truth_sha256(self) -> str:
        return sha256_hex(canonical_json([t.__dict__ for t in self.truth]))


@dataclass
class _Ctx:
    rng: random.Random
    start: date
    days: int
    precision: Precision
    rows: list[dict[str, str]] = field(default_factory=list)
    used_accounts: set[str] = field(default_factory=set)
    used_tx: set[str] = field(default_factory=set)
    boundary: set[str] = field(default_factory=set)

    def account(self) -> str:
        while True:
            style = self.rng.random()
            if style < 0.4:
                acc = "KZ" + "".join(str(self.rng.randrange(10)) for _ in range(18))
            elif style < 0.75:
                acc = str(self.rng.randrange(9_007_199_254_740_993, 99_999_999_999_999_999_999))
            else:
                acc = str(self.rng.randrange(10_000_000, 9_000_000_000_000))
            if acc not in self.used_accounts:
                self.used_accounts.add(acc)
                return acc

    def transfer(self, sender: str, receiver: str, amount_minor: int, day: int, status: str = "posted") -> str:
        while True:
            tx = f"{self.rng.getrandbits(64):016x}"
            if tx not in self.used_tx:
                self.used_tx.add(tx)
                break
        d = self.start + timedelta(days=day)
        row = {
            "source_transaction_id": tx,
            "sender_account_id": sender,
            "receiver_account_id": receiver,
            "amount_minor": str(amount_minor),
            "currency": "KZT",
            "observed_date": d.isoformat(),
            "occurred_at": "",
            "status": status,
        }
        if self.precision == "timestamp":
            seconds = self.rng.randrange(8 * 3600, 21 * 3600)
            ts = datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(seconds=seconds)
            row["occurred_at"] = ts.isoformat().replace("+00:00", "Z")
        self.rows.append(row)
        return tx

    def kzt(self, lo: int, hi: int) -> int:
        """Random amount in tiyn between ``lo`` and ``hi`` whole tenge."""
        return self.rng.randrange(lo, hi) * 100 + self.rng.randrange(100)


def _collection_funnel(ctx: _Ctx, sid: str, *, at_boundary: bool = False) -> ScenarioTruth:
    """S1: several feeders consolidate into one account, which forwards most funds onwards."""
    r = ctx.rng
    center = ctx.account()
    feeders = [ctx.account() for _ in range(r.randint(4, 7))]
    d0 = r.randrange(2, ctx.days - 12)
    txs: list[str] = []
    total = 0
    last_in = d0
    for f in feeders:
        amount = ctx.kzt(150_000, 900_000)
        day = d0 + r.randrange(0, 3)
        last_in = max(last_in, day)
        txs.append(ctx.transfer(f, center, amount, day))
        total += amount
    downstream: list[str] = []
    if at_boundary:
        ctx.boundary.add(center)  # the collection stops here: onward movement is unobserved
    else:
        downstream = [ctx.account() for _ in range(r.randint(1, 2))]
        forwarded = total * r.randint(80, 95) // 100
        share = forwarded // len(downstream)
        for i, d in enumerate(downstream):
            amount = share if i < len(downstream) - 1 else forwarded - share * (len(downstream) - 1)
            txs.append(ctx.transfer(center, d, amount, last_in + r.randint(1, 3)))
    return ScenarioTruth(
        scenario_id=sid,
        family="S1_collection_funnel_boundary" if at_boundary else "S1_collection_funnel",
        label="suspicious",
        difficulty="hard" if at_boundary else "easy",
        accounts=[*feeders, center, *downstream],
        source_transaction_ids=txs,
        notes="centre at declared collection boundary" if at_boundary else "consolidation then onward transfer",
    )


def _layering_chain(
    ctx: _Ctx, sid: str, *, mode: Literal["forward", "reverse", "same_day"] = "forward"
) -> ScenarioTruth:
    """S2 (forward), N8 (reverse chronology, legitimate by construction), same-day ambiguity."""
    r = ctx.rng
    hops = r.randint(3, 4)
    path = [ctx.account() for _ in range(hops + 1)]
    amount = ctx.kzt(400_000, 2_000_000)
    day = r.randrange(1, ctx.days - 4 * hops - 2)
    days: list[int] = []
    for _ in range(hops):
        days.append(day)
        day += r.randint(1, 3)
    if mode == "reverse":
        days = list(reversed(days))
    elif mode == "same_day":
        days = [days[0]] * hops
    txs: list[str] = []
    for i in range(hops):
        txs.append(ctx.transfer(path[i], path[i + 1], amount, days[i]))
        amount = amount * r.randint(95, 99) // 100  # small "fees" at each hop
    family = {
        "forward": "S2_layering_chain",
        "reverse": "N8_reverse_chronology_chain",
        "same_day": "H_same_day_chain",
    }[mode]
    return ScenarioTruth(
        scenario_id=sid,
        family=family,
        label="legitimate" if mode == "reverse" else "suspicious",
        difficulty="easy" if mode == "forward" else "hard",
        accounts=path,
        source_transaction_ids=txs,
        notes={
            "forward": "multi-hop pass-through with increasing dates",
            "reverse": "structurally identical path whose later legs precede earlier ones",
            "same_day": "all legs on one day with day-only precision",
        }[mode],
    )


def _payroll(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """N1: an employer funded by two clients pays many employees on a payroll date."""
    r = ctx.rng
    employer = ctx.account()
    clients = [ctx.account() for _ in range(2)]
    employees = [ctx.account() for _ in range(r.randint(10, 18))]
    txs = [ctx.transfer(c, employer, ctx.kzt(3_000_000, 6_000_000), r.randrange(0, 5)) for c in clients]
    payday = min(ctx.days - 2, 24)
    for e in employees:
        txs.append(ctx.transfer(employer, e, ctx.kzt(250_000, 600_000), payday))
    return ScenarioTruth(
        sid, "N1_payroll", "legitimate", "medium", [employer, *clients, *employees], txs, "fan-out payroll"
    )


def _merchant_settlement(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """N2: customers pay a processor that settles to merchants on a fixed schedule."""
    r = ctx.rng
    processor = ctx.account()
    customers = [ctx.account() for _ in range(r.randint(15, 25))]
    merchants = [ctx.account() for _ in range(r.randint(5, 8))]
    others = [ctx.account() for _ in range(6)]
    txs: list[str] = []
    pending = 0
    for day in range(ctx.days):
        for c in customers:
            if r.random() < 0.08:
                amount = ctx.kzt(5_000, 40_000)
                txs.append(ctx.transfer(c, processor, amount, day))
                pending += amount
            if r.random() < 0.05:
                txs.append(ctx.transfer(c, r.choice(others), ctx.kzt(2_000, 30_000), day))
        if day % 3 == 2 and pending > 0:
            payout = pending * 98 // 100
            share = payout // len(merchants)
            for m in merchants:
                txs.append(ctx.transfer(processor, m, share, day))
            pending = 0
    return ScenarioTruth(
        sid,
        "N2_merchant_settlement",
        "legitimate",
        "hard",
        [processor, *customers, *merchants],
        txs,
        "processor hub",
    )


def _reimbursements(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """N4: friends/family reciprocal transfers of modest size."""
    r = ctx.rng
    people = [ctx.account() for _ in range(4)]
    txs: list[str] = []
    for _ in range(10):
        a, b = r.sample(people, 2)
        txs.append(ctx.transfer(a, b, ctx.kzt(2_000, 60_000), r.randrange(0, ctx.days)))
    return ScenarioTruth(sid, "N4_reimbursement", "legitimate", "easy", people, txs, "small reciprocal transfers")


def _background(ctx: _Ctx, n_accounts: int, n_transfers: int) -> None:
    """Unlabelled background activity; may contain coincidental structures like real data."""
    r = ctx.rng
    accounts = [ctx.account() for _ in range(n_accounts)]
    for _ in range(n_transfers):
        a, b = r.sample(accounts, 2)
        ctx.transfer(a, b, ctx.kzt(1_000, 120_000), r.randrange(0, ctx.days))


Builder = Callable[[_Ctx, str], ScenarioTruth]
SUITES: dict[str, dict[str, Any]] = {
    "demo-v1": {
        "description": "Mixed demonstration suite: suspicious formations, legitimate lookalikes and hard negatives.",
        "scenarios": [
            ("S1_collection_funnel", lambda c, s: _collection_funnel(c, s)),
            ("S2_layering_chain", lambda c, s: _layering_chain(c, s, mode="forward")),
            ("H_same_day_chain", lambda c, s: _layering_chain(c, s, mode="same_day")),
            ("S1_collection_funnel_boundary", lambda c, s: _collection_funnel(c, s, at_boundary=True)),
            ("N1_payroll", _payroll),
            ("N2_merchant_settlement", _merchant_settlement),
            ("N4_reimbursement", _reimbursements),
            ("N8_reverse_chronology_chain", lambda c, s: _layering_chain(c, s, mode="reverse")),
        ],
        "background": (60, 140),
    },
    "funnel-only-v1": {
        "description": "A single collection funnel with onward transfer and light background noise.",
        "scenarios": [("S1_collection_funnel", lambda c, s: _collection_funnel(c, s))],
        "background": (20, 40),
    },
    "lookalikes-v1": {
        "description": (
            "Legitimate lookalikes only: payroll, merchant settlement, reimbursements, reverse-chronology path."
        ),
        "scenarios": [
            ("N1_payroll", _payroll),
            ("N2_merchant_settlement", _merchant_settlement),
            ("N4_reimbursement", _reimbursements),
            ("N8_reverse_chronology_chain", lambda c, s: _layering_chain(c, s, mode="reverse")),
        ],
        "background": (40, 90),
    },
}


def generate(
    suite: str, seed: int, *, precision: Precision = "day", start: date = date(2026, 7, 1), days: int = 30
) -> GeneratedDataset:
    if suite not in SUITES:
        raise KeyError(f"unknown suite {suite!r}")
    spec = SUITES[suite]
    ctx = _Ctx(
        rng=random.Random(f"{GENERATOR_VERSION}|{suite}|{seed}|{precision}"),
        start=start,
        days=days,
        precision=precision,
    )
    truth: list[ScenarioTruth] = []
    for index, (family, build) in enumerate(spec["scenarios"]):
        truth.append(build(ctx, f"{suite}-{seed}-{index:02d}-{family}"))
    _background(ctx, *spec["background"])
    rows = ctx.rows
    ctx.rng.shuffle(rows)  # source order carries no information
    contract = {
        "source": "synthetic",
        "generator_version": GENERATOR_VERSION,
        "time_precision": precision,
        "boundary_account_ids": sorted(ctx.boundary),
        "upstream_observed": True,
        "declared_complete": False,
    }
    return GeneratedDataset(
        suite=suite,
        seed=seed,
        precision=precision,
        rows=rows,
        coverage_contract=contract,
        truth=truth,
        window=(start, start + timedelta(days=days - 1)),
    )
