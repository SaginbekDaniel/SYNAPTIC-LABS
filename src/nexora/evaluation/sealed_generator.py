"""Independent sealed-evaluation generator ``sealed-gen-v1`` (docs/evaluation/EXPERIMENT_PROTOCOL.md).

Written separately from ``generator.py`` and *before* the hypothesis engine it evaluates,
so that its mechanisms were not shaped by that engine's features. It differs from
``bench-v1`` on purpose:

* 45-day window, different amount distributions (log-uniform), different timing models;
* label-independent coverage contract: the declared collection boundary is a uniform
  random sample of *all* accounts (accounts "held at other banks"), plus the centres of
  boundary scenarios — so a boundary declaration carries no label information
  (``bench-v1`` declared only planted fraud centres, audit finding L-01);
* complete truth account lists (every account a scenario creates is listed);
* new legitimate families that share the shape of fraud (event ticketing and charity
  campaigns with one-off payers and fast pass-through, payroll whose recipients spend
  onward, cash pooling) and adversarial fraud built to evade the obvious features
  (mule collection with *recurring* feeders, token activation payments, slow funnels,
  low-value coordination below materiality floors, partially observed chains).

Some of these cases are observationally indistinguishable from their counterpart on
transaction data alone. That is intended: the evaluation must reward honest uncertainty,
not a generator-specific shortcut.

Ground truth is returned separately and never enters rows or the coverage contract.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from nexora.evaluation.generator import GeneratedDataset, ScenarioTruth

SEALED_GENERATOR_VERSION = "sealed-gen-v1"
SEALED_SUITE = "sealed-v1"
WINDOW_DAYS = 45
BOUNDARY_SAMPLE_RATE = 0.06  # share of all accounts declared at the collection boundary, label-blind


@dataclass
class _World:
    rng: random.Random
    start: date
    timestamped: bool
    rows: list[dict[str, str]] = field(default_factory=list)
    accounts: set[str] = field(default_factory=set)
    tx_ids: set[str] = field(default_factory=set)
    scenario_boundary: set[str] = field(default_factory=set)

    def new_account(self) -> str:
        while True:
            kind = self.rng.randrange(3)
            if kind == 0:
                acc = "KZ" + f"{self.rng.getrandbits(60):018d}"[:18]
            elif kind == 1:
                acc = str(self.rng.randrange(10**15, 10**20))
            else:
                acc = f"{self.rng.randrange(10**7, 10**12)}"
            if acc not in self.accounts:
                self.accounts.add(acc)
                return acc

    def accounts_n(self, n: int) -> list[str]:
        return [self.new_account() for _ in range(n)]

    def pay(self, sender: str, receiver: str, amount_minor: int, day: float) -> str:
        """``day`` may be fractional; the fraction becomes the intraday time when timestamped."""
        day = min(max(day, 0.0), WINDOW_DAYS - 0.01)
        whole = int(day)
        d = self.start + timedelta(days=whole)
        while True:
            tid = "T" + f"{self.rng.getrandbits(72):018x}"
            if tid not in self.tx_ids:
                self.tx_ids.add(tid)
                break
        occurred = ""
        if self.timestamped:
            secs = int((day - whole) * 86_400) if day != whole else self.rng.randrange(7 * 3600, 22 * 3600)
            ts = datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(seconds=secs)
            occurred = ts.isoformat().replace("+00:00", "Z")
        self.rows.append(
            {
                "source_transaction_id": tid,
                "sender_account_id": sender,
                "receiver_account_id": receiver,
                "amount_minor": str(max(1, int(amount_minor))),
                "currency": "KZT",
                "observed_date": d.isoformat(),
                "occurred_at": occurred,
                "status": "posted",
            }
        )
        return tid

    def money(self, lo_tenge: int, hi_tenge: int) -> int:
        """Log-uniform amount in tiyn: small amounts are more common than large ones."""
        v = math.exp(self.rng.uniform(math.log(lo_tenge), math.log(hi_tenge)))
        return int(v) * 100 + self.rng.randrange(100)


@dataclass
class _Plan:
    family: str
    label: str
    difficulty: str
    notes: str
    accounts: list[str] = field(default_factory=list)
    txs: list[str] = field(default_factory=list)


def _start_day(w: _World, need: int) -> float:
    return float(w.rng.randrange(0, max(1, WINDOW_DAYS - need)))


# ----------------------------------------------------------------------------------------
# Suspicious families
# ----------------------------------------------------------------------------------------
def sx_mule_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("SX1_mule_collection", "suspicious", "easy", "one-off mule deposits consolidated and moved on")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(3, 9))
    exits = w.accounts_n(r.randint(1, 3))
    t0 = _start_day(w, 20)
    spread = r.uniform(0.5, 6)
    total, last = 0, t0
    for m in mules:
        a = w.money(120_000, 1_200_000)
        d = t0 + r.uniform(0, spread)
        last = max(last, d)
        p.txs.append(w.pay(m, hub, a, d))
        total += a
    moved = total * r.randint(50, 98) // 100
    for e in exits:
        share = moved // len(exits)
        p.txs.append(w.pay(hub, e, share, last + r.uniform(0.1, 8)))
    p.accounts = [hub, *mules, *exits]
    return p


def sx_activation_collection(w: _World) -> _Plan:
    """Adversarial: the hub first sends each mule a small 'activation' payment."""
    r = w.rng
    p = _Plan("SX2_activation_collection", "suspicious", "adversarial", "hub pays mules 5-15% first, then collects")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(4, 8))
    exit_acc = w.new_account()
    t0 = _start_day(w, 20)
    total = 0
    for m in mules:
        a = w.money(200_000, 1_000_000)
        p.txs.append(w.pay(hub, m, a * r.randint(5, 15) // 100, t0))
        p.txs.append(w.pay(m, hub, a, t0 + r.uniform(1, 4)))
        total += a
    p.txs.append(w.pay(hub, exit_acc, total * r.randint(70, 95) // 100, t0 + r.uniform(5, 9)))
    p.accounts = [hub, *mules, exit_acc]
    return p


def sx_boundary_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan(
        "SX3_boundary_collection", "suspicious", "hard", "consolidation at an account whose outflow is unobserved"
    )
    hub = w.new_account()
    mules = w.accounts_n(r.randint(4, 8))
    t0 = _start_day(w, 10)
    for m in mules:
        p.txs.append(w.pay(m, hub, w.money(150_000, 900_000), t0 + r.uniform(0, 4)))
    w.scenario_boundary.add(hub)
    p.accounts = [hub, *mules]
    return p


def sx_recurring_mules(w: _World) -> _Plan:
    """Adversarial: each mule deposits 2-3 times over two weeks, imitating regular customers."""
    r = w.rng
    p = _Plan("SX4_recurring_mule_collection", "suspicious", "adversarial", "mules imitate recurring customers")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(4, 7))
    exits = w.accounts_n(r.randint(1, 2))
    t0 = _start_day(w, 25)
    total, last = 0, t0
    for m in mules:
        for k in range(r.randint(2, 3)):
            a = w.money(80_000, 500_000)
            d = t0 + k * r.uniform(4, 7) + r.uniform(0, 1)
            last = max(last, d)
            p.txs.append(w.pay(m, hub, a, d))
            total += a
    for e in exits:
        p.txs.append(w.pay(hub, e, total * r.randint(75, 95) // 100 // len(exits), last + r.uniform(0.5, 3)))
    p.accounts = [hub, *mules, *exits]
    return p


def sx_slow_collection(w: _World) -> _Plan:
    """Low-and-slow: deposits trickle in over 2-3 weeks; the hub forwards in several tranches."""
    r = w.rng
    p = _Plan("SX5_slow_collection", "suspicious", "hard", "deposits spread over weeks, forwarded in tranches")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(5, 9))
    exit_acc = w.new_account()
    t0 = _start_day(w, 32)
    pending = 0
    events = sorted((t0 + r.uniform(0, 21), m) for m in mules)
    for d, m in events:
        a = w.money(150_000, 800_000)
        p.txs.append(w.pay(m, hub, a, d))
        pending += a
        if pending > 1_500_000_00 and r.random() < 0.6:
            p.txs.append(w.pay(hub, exit_acc, pending * 9 // 10, d + r.uniform(1, 5)))
            pending = 0
    if pending:
        p.txs.append(w.pay(hub, exit_acc, pending * 9 // 10, events[-1][0] + r.uniform(1, 5)))
    p.accounts = [hub, *mules, exit_acc]
    return p


def sx_layering(w: _World) -> _Plan:
    r = w.rng
    hops = r.randint(3, 6)
    p = _Plan("SX6_layering_chain", "suspicious", "medium", f"{hops}-hop pass-through with fees and jitter")
    path = w.accounts_n(hops + 1)
    a = w.money(500_000, 4_000_000)
    d = _start_day(w, hops * 5 + 2)
    for i in range(hops):
        p.txs.append(w.pay(path[i], path[i + 1], a, d))
        a = a * r.randint(92, 99) // 100
        d += r.uniform(0.2, 5)
    p.accounts = path
    return p


def sx_partial_chain(w: _World) -> _Plan:
    """A layering chain with one leg missing from the extract (incomplete observation)."""
    r = w.rng
    p = _Plan("SX7_partially_observed_chain", "suspicious", "hard", "one hop of a 5-6 hop chain is not in the data")
    hops = r.randint(5, 6)
    path = w.accounts_n(hops + 1)
    missing = r.randrange(1, hops - 1)
    a = w.money(600_000, 3_000_000)
    d = _start_day(w, hops * 4 + 2)
    for i in range(hops):
        if i != missing:
            p.txs.append(w.pay(path[i], path[i + 1], a, d))
        a = a * r.randint(94, 99) // 100
        d += r.uniform(0.5, 3)
    p.accounts = path
    return p


def sx_distribution(w: _World, terminal: bool) -> _Plan:
    r = w.rng
    fam = "SX9_distribution_terminal" if terminal else "SX8_mule_distribution"
    p = _Plan(fam, "suspicious", "hard" if terminal else "medium", "proceeds split across mules")
    src = w.accounts_n(r.randint(1, 3))
    hub = w.new_account()
    mules = w.accounts_n(r.randint(5, 12))
    exits = [] if terminal else w.accounts_n(r.randint(1, 3))
    t0 = _start_day(w, 16)
    total = 0
    for s in src:
        a = w.money(1_500_000, 8_000_000)
        p.txs.append(w.pay(s, hub, a, t0 + r.uniform(0, 1.5)))
        total += a
    dispersed = total * r.randint(80, 98) // 100
    for m in mules:
        part = dispersed // len(mules) * r.randint(80, 120) // 100
        d = t0 + r.uniform(1, 4)
        p.txs.append(w.pay(hub, m, part, d))
        if exits and r.random() < 0.85:
            p.txs.append(w.pay(m, r.choice(exits), part * r.randint(80, 97) // 100, d + r.uniform(0.2, 4)))
    p.accounts = [*src, hub, *mules, *exits]
    return p


def sx_circular(w: _World) -> _Plan:
    r = w.rng
    n = r.randint(3, 6)
    p = _Plan("SX10_round_trip", "suspicious", "medium", f"funds return to the origin through {n} accounts")
    ring = w.accounts_n(n)
    a = w.money(700_000, 5_000_000)
    d = _start_day(w, n * 4 * 2)
    for _ in range(r.choice((1, 1, 2))):
        for i in range(n):
            p.txs.append(w.pay(ring[i], ring[(i + 1) % n], a, d))
            a = a * r.randint(95, 99) // 100
            d += r.uniform(0.3, 3)
    p.accounts = ring
    return p


def sx_low_value(w: _World) -> _Plan:
    """Coordinated deposits below every materiality floor (expected to be missed; measures the floor)."""
    r = w.rng
    p = _Plan("SX11_low_value_coordination", "suspicious", "adversarial", "many small one-off deposits, then onward")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(6, 10))
    exit_acc = w.new_account()
    t0 = _start_day(w, 10)
    total = 0
    for m in mules:
        a = w.money(3_000, 6_000)
        p.txs.append(w.pay(m, hub, a, t0 + r.uniform(0, 2)))
        total += a
    p.txs.append(w.pay(hub, exit_acc, total * 9 // 10, t0 + r.uniform(2.5, 5)))
    p.accounts = [hub, *mules, exit_acc]
    return p


# ----------------------------------------------------------------------------------------
# Legitimate families
# ----------------------------------------------------------------------------------------
def lx_rent_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LX1_rent_collection", "legitimate", "hard", "tenants pay monthly; landlord pays vendors and owner")
    landlord = w.new_account()
    tenants = w.accounts_n(r.randint(8, 20))
    vendors = w.accounts_n(r.randint(2, 4))
    owner = w.new_account()
    collected = 0
    for month_start in (0, 30):
        for t in tenants:
            if month_start + 5 < WINDOW_DAYS:
                a = w.money(150_000, 450_000)
                p.txs.append(w.pay(t, landlord, a, month_start + r.uniform(0, 5)))
                collected += a
        for v in vendors:
            p.txs.append(w.pay(landlord, v, w.money(100_000, 600_000), month_start + r.uniform(8, 12)))
        if month_start + 10 < WINDOW_DAYS:
            p.txs.append(w.pay(landlord, owner, collected * r.randint(40, 70) // 100, month_start + r.uniform(9, 11)))
            collected = 0
    p.accounts = [landlord, *tenants, *vendors, owner]
    return p


def lx_marketplace(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LX2_marketplace_with_refunds", "legitimate", "hard", "platform settles sellers daily, refunds buyers")
    platform = w.new_account()
    buyers = w.accounts_n(r.randint(15, 30))
    sellers = w.accounts_n(r.randint(4, 8))
    pending = 0
    for day in range(WINDOW_DAYS):
        for b in buyers:
            if r.random() < 0.06:
                a = w.money(3_000, 80_000)
                p.txs.append(w.pay(b, platform, a, day + r.random()))
                pending += a
                if r.random() < 0.08:
                    p.txs.append(w.pay(platform, b, a, day + 1 + r.uniform(0, 3)))
                    pending -= a
        if day % 2 == 1 and pending > 0:
            for s in sellers:
                p.txs.append(w.pay(platform, s, pending * 95 // 100 // len(sellers), day + 0.9))
            pending = 0
    p.accounts = [platform, *buyers, *sellers]
    return p


def lx_payroll_spending(w: _World) -> _Plan:
    """Employees spend part of their salary within days (recipients move money onward)."""
    r = w.rng
    p = _Plan("LX3_payroll_with_spending", "legitimate", "hard", "payroll whose recipients spend at shops")
    company = w.new_account()
    customers = w.accounts_n(r.randint(3, 6))
    staff = w.accounts_n(r.randint(6, 15))
    shops = w.accounts_n(r.randint(3, 6))
    for c in customers:
        for _ in range(r.randint(2, 4)):
            p.txs.append(w.pay(c, company, w.money(1_000_000, 4_000_000), r.uniform(0, WINDOW_DAYS)))
    for payday in (14.5, 29.5, 44.0):
        for s in staff:
            sal = w.money(250_000, 700_000)
            p.txs.append(w.pay(company, s, sal, payday))
            for _ in range(r.randint(0, 2)):
                p.txs.append(w.pay(s, r.choice(shops), sal * r.randint(5, 30) // 100, payday + r.uniform(0.2, 6)))
    p.accounts = [company, *customers, *staff, *shops]
    return p


def lx_remittance(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LX4_family_remittance", "legitimate", "hard", "worker sends part of salary to many relatives")
    employer = w.new_account()
    worker = w.new_account()
    relatives = w.accounts_n(r.randint(4, 8))
    pay = _start_day(w, 6)
    salary = w.money(500_000, 1_500_000)
    p.txs.append(w.pay(employer, worker, salary, pay))
    for rel in relatives:
        p.txs.append(w.pay(worker, rel, salary * r.randint(4, 12) // 100, pay + r.uniform(0, 2)))
    p.accounts = [employer, worker, *relatives]
    return p


def lx_cash_pooling(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LX5_cash_pooling", "legitimate", "hard", "subsidiaries sweep balances to the parent weekly")
    parent = w.new_account()
    subs = w.accounts_n(r.randint(3, 6))
    banks = w.accounts_n(2)
    for s in subs:
        clients = w.accounts_n(r.randint(2, 5))
        p.accounts.extend(clients)
        for c in clients:
            for _ in range(r.randint(2, 5)):
                p.txs.append(w.pay(c, s, w.money(200_000, 2_000_000), r.uniform(0, WINDOW_DAYS)))
        for week in range(r.randrange(0, 4), WINDOW_DAYS - 1, 7):
            p.txs.append(w.pay(s, parent, w.money(1_000_000, 6_000_000), week + 0.75))
    for week in range(5, WINDOW_DAYS - 1, 7):
        p.txs.append(w.pay(parent, r.choice(banks), w.money(5_000_000, 20_000_000), week + 0.5))
    p.accounts = [parent, *subs, *banks, *p.accounts]
    return p


def lx_lending(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LX6_lending", "legitimate", "hard", "loans disbursed, instalments collected")
    lender = w.new_account()
    funder = w.new_account()
    borrowers = w.accounts_n(r.randint(5, 10))
    p.txs.append(w.pay(funder, lender, w.money(20_000_000, 40_000_000), 0.5))
    for b in borrowers:
        principal = w.money(400_000, 3_000_000)
        d = r.uniform(1, 8)
        p.txs.append(w.pay(lender, b, principal, d))
        for k in range(1, 3):
            if d + 15 * k < WINDOW_DAYS:
                p.txs.append(w.pay(b, lender, principal * r.randint(15, 30) // 100, d + 15 * k + r.uniform(-1, 1)))
    p.accounts = [lender, funder, *borrowers]
    return p


def lx_event_ticketing(w: _World) -> _Plan:
    """One-off buyers pay an organiser within days; the organiser pays venue and artists shortly after.

    Shares every transaction-level property of a mule collection. Expected to be
    indistinguishable without merchant-category data.
    """
    r = w.rng
    p = _Plan("LX7_event_ticketing", "legitimate", "adversarial", "one-off ticket buyers, fast payout to venue")
    organiser = w.new_account()
    buyers = w.accounts_n(r.randint(6, 25))
    payees = w.accounts_n(r.randint(1, 3))
    t0 = _start_day(w, 14)
    total = 0
    for b in buyers:
        a = w.money(20_000, 250_000)
        p.txs.append(w.pay(b, organiser, a, t0 + r.uniform(0, 5)))
        total += a
    for v in payees:
        p.txs.append(w.pay(organiser, v, total * r.randint(60, 85) // 100 // len(payees), t0 + r.uniform(5, 9)))
    p.accounts = [organiser, *buyers, *payees]
    return p


def lx_charity(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LX8_charity_campaign", "legitimate", "adversarial", "one-off donors, transfer to beneficiary")
    fund = w.new_account()
    donors = w.accounts_n(r.randint(8, 25))
    beneficiary = w.new_account()
    t0 = _start_day(w, 20)
    total = 0
    for dnr in donors:
        a = w.money(10_000, 300_000)
        p.txs.append(w.pay(dnr, fund, a, t0 + r.uniform(0, 10)))
        total += a
    p.txs.append(w.pay(fund, beneficiary, total * r.randint(85, 98) // 100, t0 + r.uniform(10, 16)))
    p.accounts = [fund, *donors, beneficiary]
    return p


def lx_supplier(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LX9_wholesale_supplier", "legitimate", "hard", "recurring customers, scheduled producer payments")
    firm = w.new_account()
    customers = w.accounts_n(r.randint(6, 14))
    producers = w.accounts_n(r.randint(5, 9))
    for c in customers:
        for _ in range(r.randint(2, 6)):
            p.txs.append(w.pay(c, firm, w.money(100_000, 900_000), r.uniform(0, WINDOW_DAYS)))
    for pay in (r.uniform(9, 12), r.uniform(24, 27), r.uniform(39, 42)):
        for pr in producers:
            p.txs.append(w.pay(firm, pr, w.money(200_000, 1_500_000), pay))
    p.accounts = [firm, *customers, *producers]
    return p


def _background(w: _World) -> None:
    r = w.rng
    people = w.accounts_n(r.randint(80, 180))
    for _ in range(r.randint(200, 600)):
        a, b = r.sample(people, 2)
        w.pay(a, b, w.money(1_000, 150_000), r.uniform(0, WINDOW_DAYS))


SUSPICIOUS: list[tuple[str, int, Callable[[_World], _Plan]]] = [
    ("SX1_mule_collection", 3, sx_mule_collection),
    ("SX2_activation_collection", 1, sx_activation_collection),
    ("SX3_boundary_collection", 1, sx_boundary_collection),
    ("SX4_recurring_mule_collection", 1, sx_recurring_mules),
    ("SX5_slow_collection", 1, sx_slow_collection),
    ("SX6_layering_chain", 2, sx_layering),
    ("SX7_partially_observed_chain", 1, sx_partial_chain),
    ("SX8_mule_distribution", 2, lambda w: sx_distribution(w, False)),
    ("SX9_distribution_terminal", 1, lambda w: sx_distribution(w, True)),
    ("SX10_round_trip", 2, sx_circular),
    ("SX11_low_value_coordination", 1, sx_low_value),
]
LEGITIMATE: list[tuple[str, int, Callable[[_World], _Plan]]] = [
    ("LX1_rent_collection", 1, lx_rent_collection),
    ("LX2_marketplace_with_refunds", 1, lx_marketplace),
    ("LX3_payroll_with_spending", 1, lx_payroll_spending),
    ("LX4_family_remittance", 1, lx_remittance),
    ("LX5_cash_pooling", 1, lx_cash_pooling),
    ("LX6_lending", 1, lx_lending),
    ("LX7_event_ticketing", 1, lx_event_ticketing),
    ("LX8_charity_campaign", 1, lx_charity),
    ("LX9_wholesale_supplier", 1, lx_supplier),
]


def generate_sealed(seed: int, start: date = date(2026, 3, 2)) -> GeneratedDataset:
    meta = random.Random(f"{SEALED_GENERATOR_VERSION}|meta|{seed}")
    timestamped = meta.random() < 0.4
    w = _World(rng=random.Random(f"{SEALED_GENERATOR_VERSION}|{seed}"), start=start, timestamped=timestamped)
    picks = [
        *w.rng.choices(SUSPICIOUS, weights=[x[1] for x in SUSPICIOUS], k=w.rng.randint(2, 5)),
        *w.rng.choices(LEGITIMATE, weights=[x[1] for x in LEGITIMATE], k=w.rng.randint(3, 6)),
    ]
    w.rng.shuffle(picks)
    truth: list[ScenarioTruth] = []
    for index, (_, _, build) in enumerate(picks):
        plan = build(w)
        truth.append(
            ScenarioTruth(
                scenario_id=f"{SEALED_SUITE}-{seed}-{index:02d}-{plan.family}",
                family=plan.family,
                label=plan.label,  # type: ignore[arg-type]
                difficulty=plan.difficulty,  # type: ignore[arg-type]
                accounts=list(dict.fromkeys(plan.accounts)),
                source_transaction_ids=plan.txs,
                notes=plan.notes,
            )
        )
    _background(w)
    rows = w.rows
    w.rng.shuffle(rows)
    everyone = sorted(w.accounts)
    blind = {a for a in everyone if meta.random() < BOUNDARY_SAMPLE_RATE}  # independent of labels
    contract = {
        "source": "synthetic",
        "generator_version": SEALED_GENERATOR_VERSION,
        "time_precision": "timestamp" if timestamped else "day",
        "boundary_account_ids": sorted(blind | w.scenario_boundary),
        "upstream_observed": True,
        "declared_complete": False,
    }
    return GeneratedDataset(
        suite=SEALED_SUITE,
        seed=seed,
        precision="timestamp" if timestamped else "day",
        rows=rows,
        coverage_contract=contract,
        truth=truth,
        window=(start, start + timedelta(days=WINDOW_DAYS - 1)),
    )
