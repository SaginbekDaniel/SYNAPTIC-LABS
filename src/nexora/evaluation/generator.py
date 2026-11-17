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
BENCH_GENERATOR_VERSION = "synthetic-bench-v1"
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


def _collection_funnel(
    ctx: _Ctx,
    sid: str,
    *,
    at_boundary: bool = False,
    feeders_range: tuple[int, int] = (4, 7),
    feeder_spread_days: int = 3,
    forward_lag: tuple[int, int] = (1, 3),
    forward_pct: tuple[int, int] = (80, 95),
) -> ScenarioTruth:
    """S1: several feeders consolidate into one account, which forwards most funds onwards.

    Defaults reproduce ``synthetic-gen-v1`` exactly; the benchmark suite widens the ranges
    (more/fewer feeders, slower onward movement, lower onward share) so some instances
    fall outside detector thresholds, as real cases do.
    """
    r = ctx.rng
    center = ctx.account()
    feeders = [ctx.account() for _ in range(r.randint(*feeders_range))]
    d0 = r.randrange(2, ctx.days - 12)
    txs: list[str] = []
    total = 0
    last_in = d0
    for f in feeders:
        amount = ctx.kzt(150_000, 900_000)
        day = d0 + r.randrange(0, feeder_spread_days)
        last_in = max(last_in, day)
        txs.append(ctx.transfer(f, center, amount, day))
        total += amount
    downstream: list[str] = []
    if at_boundary:
        ctx.boundary.add(center)  # the collection stops here: onward movement is unobserved
    else:
        downstream = [ctx.account() for _ in range(r.randint(1, 2))]
        forwarded = total * r.randint(*forward_pct) // 100
        share = forwarded // len(downstream)
        for i, d in enumerate(downstream):
            amount = share if i < len(downstream) - 1 else forwarded - share * (len(downstream) - 1)
            txs.append(ctx.transfer(center, d, amount, min(ctx.days - 1, last_in + r.randint(*forward_lag))))
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
    ctx: _Ctx,
    sid: str,
    *,
    mode: Literal["forward", "reverse", "same_day"] = "forward",
    hops_range: tuple[int, int] = (3, 4),
    hop_lag: tuple[int, int] = (1, 3),
    keep_pct: tuple[int, int] = (95, 99),
) -> ScenarioTruth:
    """S2 (forward), N8 (reverse chronology, legitimate by construction), same-day ambiguity."""
    r = ctx.rng
    hops = r.randint(*hops_range)
    path = [ctx.account() for _ in range(hops + 1)]
    amount = ctx.kzt(400_000, 2_000_000)
    day = r.randrange(1, max(2, ctx.days - (hop_lag[1] + 1) * hops - 2))
    days: list[int] = []
    for _ in range(hops):
        days.append(day)
        day += r.randint(*hop_lag)
    if mode == "reverse":
        days = list(reversed(days))
    elif mode == "same_day":
        days = [days[0]] * hops
    txs: list[str] = []
    for i in range(hops):
        txs.append(ctx.transfer(path[i], path[i + 1], amount, days[i]))
        amount = amount * r.randint(*keep_pct) // 100  # small "fees" at each hop
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


def _split(total: int, parts: int, rng: random.Random, lo: int = 60, hi: int = 140) -> list[int]:
    """Split an exact integer amount into ``parts`` uneven positive pieces (sum preserved)."""
    weights = [rng.randint(lo, hi) for _ in range(parts)]
    w_total = sum(weights)
    pieces = [total * w // w_total for w in weights]
    pieces[-1] += total - sum(pieces)
    return pieces


def _distribution(ctx: _Ctx, sid: str, *, terminal: bool = False) -> ScenarioTruth:
    """S3: proceeds land on a distributor that quickly splits them across many recipients.

    Recipients (money mules) forward most of what they receive to a few exit accounts,
    unless ``terminal`` — then onward movement is simply not observed.
    """
    r = ctx.rng
    distributor = ctx.account()
    sources = [ctx.account() for _ in range(r.randint(1, 2))]
    recipients = [ctx.account() for _ in range(r.randint(5, 11))]
    d0 = r.randrange(1, ctx.days - 12)
    txs: list[str] = []
    total_in = 0
    last_in = d0
    for src in sources:
        amount = ctx.kzt(2_000_000, 6_000_000)
        day = d0 + r.randrange(0, 2)
        last_in = max(last_in, day)
        txs.append(ctx.transfer(src, distributor, amount, day))
        total_in += amount
    dispersed = total_in * r.randint(85, 98) // 100
    base = last_in + r.randint(0, 2)
    exits = [] if terminal else [ctx.account() for _ in range(r.randint(1, 3))]
    for rcpt, amount in zip(recipients, _split(dispersed, len(recipients), r), strict=True):
        day = base + r.randrange(0, 2)
        txs.append(ctx.transfer(distributor, rcpt, amount, day))
        if exits:
            onward = amount * r.randint(85, 98) // 100
            txs.append(ctx.transfer(rcpt, r.choice(exits), onward, min(ctx.days - 1, day + r.randint(1, 3))))
    return ScenarioTruth(
        sid,
        "S3_distribution_terminal" if terminal else "S3_coordinated_distribution",
        "suspicious",
        "hard" if terminal else "medium",
        [*sources, distributor, *recipients, *exits],
        txs,
        "rapid split of received funds across many recipients"
        + ("; onward movement unobserved" if terminal else " who forward onward"),
    )


def _circular(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """S4: funds circulate through 3-5 pass-through accounts and return to the origin."""
    r = ctx.rng
    length = r.randint(3, 5)
    members = [ctx.account() for _ in range(length)]
    rounds = 2 if length <= 4 and r.random() < 0.5 else 1
    amount = ctx.kzt(800_000, 3_000_000)
    needed = rounds * length * 2 + 4
    day = r.randrange(0, max(1, ctx.days - needed))
    txs: list[str] = []
    for _ in range(rounds):
        for i in range(length):
            txs.append(ctx.transfer(members[i], members[(i + 1) % length], amount, day))
            amount = amount * r.randint(96, 99) // 100
            day += r.randint(1, 2)
        day += r.randint(1, 3)
    return ScenarioTruth(
        sid, "S4_circular_flow", "suspicious", "medium", members, txs, f"round-trip through {length} accounts"
    )


def _scatter_gather(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """S5: a source splits funds into sub-threshold parts via mules that re-consolidate at a collector."""
    r = ctx.rng
    source = ctx.account()
    collector = ctx.account()
    mules = [ctx.account() for _ in range(r.randint(4, 8))]
    d0 = r.randrange(1, ctx.days - 12)
    txs: list[str] = []
    gathered = 0
    last_in = d0
    for m in mules:
        part = ctx.kzt(1_500_000, 1_990_000)  # just below a 2 000 000 KZT reporting-style threshold
        day = d0 + r.randrange(0, 2)
        txs.append(ctx.transfer(source, m, part, day))
        fwd = part * r.randint(95, 99) // 100
        fday = day + r.randint(1, 3)
        last_in = max(last_in, fday)
        txs.append(ctx.transfer(m, collector, fwd, fday))
        gathered += fwd
    exit_acc = ctx.account()
    txs.append(ctx.transfer(collector, exit_acc, gathered * r.randint(85, 95) // 100, last_in + r.randint(1, 3)))
    return ScenarioTruth(
        sid,
        "S5_scatter_gather",
        "suspicious",
        "medium",
        [source, *mules, collector, exit_acc],
        txs,
        "structured split through mules, then re-consolidation",
    )


def _supplier_payments(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """N3: a trading company collects revenue from recurring customers and pays regular suppliers."""
    r = ctx.rng
    company = ctx.account()
    customers = [ctx.account() for _ in range(r.randint(8, 15))]
    suppliers = [ctx.account() for _ in range(r.randint(5, 9))]
    txs: list[str] = []
    revenue = 0
    for day in range(ctx.days):
        for c in customers:
            if r.random() < 0.12:
                amount = ctx.kzt(50_000, 400_000)
                txs.append(ctx.transfer(c, company, amount, day))
                revenue += amount
    paydays = [r.randrange(8, 13), r.randrange(22, min(27, ctx.days - 1))]
    budget = max(len(suppliers) * 2 * 10_000_00, revenue * r.randint(70, 90) // 100)
    for pay_day, chunk in zip(paydays, _split(budget, 2, r), strict=True):
        for sup, amount in zip(suppliers, _split(chunk, len(suppliers), r), strict=True):
            txs.append(ctx.transfer(company, sup, amount, pay_day))
    for sup in suppliers:  # suppliers have other clients too
        for _ in range(r.randint(0, 2)):
            txs.append(ctx.transfer(ctx.account(), sup, ctx.kzt(20_000, 200_000), r.randrange(0, ctx.days)))
    return ScenarioTruth(
        sid,
        "N3_supplier_payments",
        "legitimate",
        "hard",
        [company, *customers, *suppliers],
        txs,
        "recurring revenue, scheduled supplier runs",
    )


def _family_remittance(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """N5: a salaried worker receives a salary and shortly sends fixed amounts to relatives."""
    r = ctx.rng
    employer = ctx.account()
    worker = ctx.account()
    colleagues = [ctx.account() for _ in range(r.randint(3, 6))]
    relatives = [ctx.account() for _ in range(r.randint(3, 6))]
    pay_day = r.randrange(3, ctx.days - 5)
    txs = [ctx.transfer(employer, worker, ctx.kzt(400_000, 900_000), pay_day)]
    for c in colleagues:
        txs.append(ctx.transfer(employer, c, ctx.kzt(300_000, 800_000), pay_day))
    for rel in relatives:
        txs.append(ctx.transfer(worker, rel, ctx.kzt(30_000, 120_000), pay_day + r.randrange(0, 3)))
    return ScenarioTruth(
        sid,
        "N5_family_remittance",
        "legitimate",
        "hard",
        [employer, worker, *relatives],
        txs,
        "salary followed by remittances to relatives",
    )


def _loan_repayments(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """N6: a lender disburses loans, borrowers repay on a due date, collected funds are re-lent."""
    r = ctx.rng
    investor = ctx.account()
    lender = ctx.account()
    borrowers = [ctx.account() for _ in range(r.randint(6, 12))]
    new_borrowers = [ctx.account() for _ in range(r.randint(2, 4))]
    principals = [ctx.kzt(500_000, 2_000_000) for _ in borrowers]
    txs = [ctx.transfer(investor, lender, sum(principals) + ctx.kzt(100_000, 500_000), 0)]
    for b, principal in zip(borrowers, principals, strict=True):
        txs.append(ctx.transfer(lender, b, principal, r.randrange(0, 5)))
    due = r.randrange(12, 18)
    collected = 0
    for b, principal in zip(borrowers, principals, strict=True):
        instalment = principal * r.randint(20, 35) // 100
        txs.append(ctx.transfer(b, lender, instalment, due + r.randrange(0, 2)))
        collected += instalment
    relent = collected * r.randint(30, 70) // 100
    for nb, amount in zip(new_borrowers, _split(relent, len(new_borrowers), r), strict=True):
        txs.append(ctx.transfer(lender, nb, amount, due + r.randint(2, 6)))
    return ScenarioTruth(
        sid,
        "N6_loan_repayments",
        "legitimate",
        "hard",
        [investor, lender, *borrowers, *new_borrowers],
        txs,
        "instalments collected on a due date and partly re-lent",
    )


def _treasury_sweep(ctx: _Ctx, sid: str) -> ScenarioTruth:
    """N7 (decoy): group companies sweep high-value balances around a cycle on a weekly schedule.

    Structurally a time-respecting cycle with large amounts; each company also runs
    ordinary business with its own customers and suppliers.
    """
    r = ctx.rng
    companies = [ctx.account() for _ in range(r.randint(3, 4))]
    txs: list[str] = []
    accounts = list(companies)
    for co in companies:
        clients = [ctx.account() for _ in range(r.randint(4, 8))]
        vendors = [ctx.account() for _ in range(r.randint(2, 4))]
        accounts.extend(clients)
        for day in range(ctx.days):
            for cl in clients:
                if r.random() < 0.1:
                    txs.append(ctx.transfer(cl, co, ctx.kzt(100_000, 900_000), day))
        for v in vendors:
            txs.append(ctx.transfer(co, v, ctx.kzt(300_000, 1_500_000), r.randrange(0, ctx.days)))
    amount = ctx.kzt(5_000_000, 20_000_000)
    for week_start in range(r.randrange(0, 3), ctx.days - 3, 7):
        day = week_start
        for i, co in enumerate(companies):
            txs.append(ctx.transfer(co, companies[(i + 1) % len(companies)], amount, day))
            day += r.randrange(0, 2)
        amount = amount * r.randint(97, 103) // 100
    return ScenarioTruth(
        sid,
        "N7_treasury_sweep",
        "legitimate",
        "hard",
        accounts,
        txs,
        "weekly intercompany sweep cycle",
    )


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


#: Benchmark scenario pools: (family, relative weight, builder). Parameter ranges are wider
#: than the demo suite so that some planted cases fall outside detector thresholds.
BENCH_SUSPICIOUS: list[tuple[str, int, Builder]] = [
    (
        "S1_collection_funnel",
        3,
        lambda c, s: _collection_funnel(
            c, s, feeders_range=(3, 8), feeder_spread_days=5, forward_lag=(1, 9), forward_pct=(55, 95)
        ),
    ),
    ("S1_collection_funnel_boundary", 1, lambda c, s: _collection_funnel(c, s, at_boundary=True)),
    (
        "S2_layering_chain",
        2,
        lambda c, s: _layering_chain(c, s, mode="forward", hops_range=(3, 5), hop_lag=(0, 4), keep_pct=(90, 99)),
    ),
    ("H_same_day_chain", 1, lambda c, s: _layering_chain(c, s, mode="same_day")),
    ("S3_coordinated_distribution", 2, lambda c, s: _distribution(c, s)),
    ("S3_distribution_terminal", 1, lambda c, s: _distribution(c, s, terminal=True)),
    ("S4_circular_flow", 2, _circular),
    ("S5_scatter_gather", 2, _scatter_gather),
]
BENCH_LEGITIMATE: list[tuple[str, int, Builder]] = [
    ("N1_payroll", 1, _payroll),
    ("N2_merchant_settlement", 1, _merchant_settlement),
    ("N3_supplier_payments", 1, _supplier_payments),
    ("N4_reimbursement", 1, _reimbursements),
    ("N5_family_remittance", 1, _family_remittance),
    ("N6_loan_repayments", 1, _loan_repayments),
    ("N7_treasury_sweep", 1, _treasury_sweep),
    (
        "N8_reverse_chronology_chain",
        1,
        lambda c, s: _layering_chain(c, s, mode="reverse", hops_range=(3, 5), hop_lag=(1, 4)),
    ),
]


def _bench_composition(rng: random.Random) -> list[tuple[str, Builder]]:
    def draw(pool: list[tuple[str, int, Builder]], k: int) -> list[tuple[str, Builder]]:
        picks = rng.choices(pool, weights=[w for _, w, _ in pool], k=k)
        return [(name, build) for name, _, build in picks]

    chosen = draw(BENCH_SUSPICIOUS, rng.randint(2, 4)) + draw(BENCH_LEGITIMATE, rng.randint(3, 5))
    rng.shuffle(chosen)  # generation order (and therefore id assignment) carries no class information
    return chosen


def generate(
    suite: str,
    seed: int,
    *,
    precision: Precision | None = None,
    start: date = date(2026, 7, 1),
    days: int = 30,
) -> GeneratedDataset:
    """Generate one dataset. ``precision=None`` uses the suite default (``day`` unless the
    suite randomises it per seed)."""
    if suite not in SUITES:
        raise KeyError(f"unknown suite {suite!r}")
    spec = SUITES[suite]
    version = str(spec.get("generator_version", GENERATOR_VERSION))
    if precision is None:
        if spec.get("random_precision"):
            precision = "timestamp" if random.Random(f"{version}|{suite}|{seed}|precision").random() < 0.3 else "day"
        else:
            precision = "day"
    ctx = _Ctx(
        rng=random.Random(f"{version}|{suite}|{seed}|{precision}"),
        start=start,
        days=days,
        precision=precision,
    )
    scenarios = spec["compose"](ctx.rng) if "compose" in spec else spec["scenarios"]
    truth: list[ScenarioTruth] = []
    for index, (family, build) in enumerate(scenarios):
        truth.append(build(ctx, f"{suite}-{seed}-{index:02d}-{family}"))
    bg = spec["background"]
    if callable(bg):
        bg = bg(ctx.rng)
    _background(ctx, *bg)
    rows = ctx.rows
    ctx.rng.shuffle(rows)  # source order carries no information
    contract = {
        "source": "synthetic",
        "generator_version": version,
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


SUITES["bench-v1"] = {
    "description": (
        "Benchmark suite: per seed, 2-4 suspicious and 3-5 legitimate scenarios drawn from eight typologies "
        "each, randomised parameters and background volume; 30% of seeds carry timestamps."
    ),
    "generator_version": BENCH_GENERATOR_VERSION,
    "compose": _bench_composition,
    "background": lambda rng: (rng.randint(50, 130), rng.randint(120, 360)),
    "random_precision": True,
}


def suite_families(suite: str) -> list[str]:
    """Scenario families a suite can contain (fixed list, or the pools a composed suite draws from)."""
    spec = SUITES[suite]
    if "compose" in spec:
        return [name for name, _, _ in (*BENCH_SUSPICIOUS, *BENCH_LEGITIMATE)]
    return [name for name, _ in spec["scenarios"]]
