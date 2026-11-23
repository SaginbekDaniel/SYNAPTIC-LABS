"""Sealed-evaluation generator ``sealed-gen-v2`` (docs/evaluation/EXPERIMENT_PROTOCOL_SEALED_V2.md).

``sealed-v1`` (sealed_generator.py) was evaluated once and is consumed: judging any later change on it would be
selection on the test set. This generator provides a fresh held-out split. It is written as a separate file (v1
stays byte-identical, its hash is part of the v1 protocol) and differs from v1 on purpose:

* 60-day window from a different start date; log-normal amounts (v1: log-uniform); business-hours timestamps and
  quieter weekends for ordinary activity (v1: uniform intraday times);
* changed parameter ranges for every typology v1 also has (sizes, speeds, retained shares, fees);
* new suspicious families: two-tier collection through sub-collectors, scatter-gather structuring, and a
  salary-like pass-through mule; new legitimate families: property escrow, a payroll agency, group gift
  collections, and a merchant whose outflows are held at another bank;
* **label-blind boundaries, stronger than v1**: a 5 % random sample of all accounts is declared at the collection
  boundary, and boundary *centres* exist for both labels (a suspicious collection and a legitimate merchant, both
  with unobserved outflows), so a declared boundary carries no label information;
* complete truth account lists; scenarios never share accounts.

Ground truth is returned separately and never enters rows or the coverage contract. No detector output was
used to design this generator; its unit tests check generator properties only.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from nexora.evaluation.generator import GeneratedDataset, ScenarioTruth

SEALED_V2_GENERATOR_VERSION = "sealed-gen-v2"
SEALED_V2_SUITE = "sealed-v2"
WINDOW_DAYS = 60
START = date(2026, 5, 4)  # a Monday
BOUNDARY_SAMPLE_RATE = 0.05  # share of all accounts declared at the collection boundary, label-blind


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
            kind = self.rng.randrange(4)
            if kind == 0:
                acc = "KZ" + f"{self.rng.getrandbits(64):020d}"[:18]
            elif kind == 1:
                acc = str(self.rng.randrange(10**15, 10**20))
            elif kind == 2:
                acc = f"40817{self.rng.randrange(10**14, 10**15)}"
            else:
                acc = f"{self.rng.randrange(10**8, 10**13)}"
            if acc not in self.accounts:
                self.accounts.add(acc)
                return acc

    def accounts_n(self, n: int) -> list[str]:
        return [self.new_account() for _ in range(n)]

    def pay(self, sender: str, receiver: str, amount_minor: int, day: float, *, business: bool = False) -> str:
        """``day`` may be fractional (the fraction is the intraday time when timestamped).

        ``business``: ordinary commerce — moved off weekends and timed within business hours.
        """
        day = min(max(day, 0.0), WINDOW_DAYS - 0.01)
        whole = int(day)
        if business and (self.start + timedelta(days=whole)).weekday() >= 5:
            whole = min(whole + (7 - (self.start + timedelta(days=whole)).weekday()), WINDOW_DAYS - 1)
        d = self.start + timedelta(days=whole)
        while True:
            tid = "X" + f"{self.rng.getrandbits(80):020x}"
            if tid not in self.tx_ids:
                self.tx_ids.add(tid)
                break
        occurred = ""
        if self.timestamped:
            if business or day == int(day):
                secs = int(self.rng.triangular(8.5 * 3600, 19 * 3600, 12.5 * 3600))
            else:
                secs = int((day - int(day)) * 86_400)
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

    def money(self, median_tenge: float, spread: float = 0.6, lo_tenge: int = 500) -> int:
        """Log-normal amount in tiyn around a median (``spread`` = sigma of the log), floored at ``lo_tenge``."""
        v = max(lo_tenge, median_tenge * math.exp(self.rng.gauss(0.0, spread)))
        return int(v) * 100 + self.rng.randrange(100)

    def round_money(self, median_tenge: float, step_tenge: int = 10_000) -> int:
        """A round amount (multiples of ``step_tenge``), as people move money by hand."""
        v = max(step_tenge, round(median_tenge * math.exp(self.rng.gauss(0.0, 0.4)) / step_tenge) * step_tenge)
        return int(v) * 100


@dataclass
class _Plan:
    family: str
    label: str
    difficulty: str
    notes: str
    accounts: list[str] = field(default_factory=list)
    txs: list[str] = field(default_factory=list)


def _start_day(w: _World, need: float) -> float:
    return w.rng.uniform(0, max(1.0, WINDOW_DAYS - need))


# ----------------------------------------------------------------------------------------
# Suspicious families
# ----------------------------------------------------------------------------------------
def sv_mule_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("SV1_mule_collection", "suspicious", "easy", "one-off mule deposits consolidated and moved on")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(4, 12))
    exits = w.accounts_n(r.randint(1, 4))
    t0 = _start_day(w, 18)
    spread = r.uniform(0.2, 4)
    total, last = 0, t0
    for m in mules:
        a = w.money(450_000, 0.5)
        d = t0 + r.uniform(0, spread)
        last = max(last, d)
        p.txs.append(w.pay(m, hub, a, d))
        total += a
    moved = total * r.randint(60, 95) // 100
    for e in exits:
        p.txs.append(w.pay(hub, e, moved // len(exits), last + r.uniform(0.05, 6)))
    p.accounts = [hub, *mules, *exits]
    return p


def sv_two_tier_collection(w: _World) -> _Plan:
    """New: mules pay sub-collectors, who forward to one hub, which pays out."""
    r = w.rng
    p = _Plan("SV2_two_tier_collection", "suspicious", "hard", "mules → sub-collectors → hub → exit")
    hub = w.new_account()
    exit_acc = w.new_account()
    subs = w.accounts_n(r.randint(2, 4))
    t0 = _start_day(w, 20)
    hub_total, last = 0, t0
    p.accounts = [hub, *subs, exit_acc]
    for s in subs:
        mules = w.accounts_n(r.randint(3, 6))
        p.accounts.extend(mules)
        got = 0
        for m in mules:
            a = w.money(300_000, 0.5)
            p.txs.append(w.pay(m, s, a, t0 + r.uniform(0, 3)))
            got += a
        fwd = got * r.randint(85, 97) // 100
        d = t0 + r.uniform(3, 7)
        last = max(last, d)
        p.txs.append(w.pay(s, hub, fwd, d))
        hub_total += fwd
    p.txs.append(w.pay(hub, exit_acc, hub_total * r.randint(80, 96) // 100, last + r.uniform(0.5, 4)))
    return p


def sv_scatter_gather(w: _World) -> _Plan:
    """New: one source splits a large sum across intermediaries, which all forward to one destination."""
    r = w.rng
    p = _Plan("SV3_scatter_gather", "suspicious", "medium", "structuring through 4-8 intermediaries to one account")
    source = w.new_account()
    middles = w.accounts_n(r.randint(4, 8))
    dest = w.new_account()
    t0 = _start_day(w, 8)
    for m in middles:
        part = w.round_money(400_000, 50_000)
        d = t0 + r.uniform(0, 1.5)
        p.txs.append(w.pay(source, m, part, d))
        p.txs.append(w.pay(m, dest, part * r.randint(96, 100) // 100, d + r.uniform(0.2, 3)))
    p.accounts = [source, *middles, dest]
    return p


def sv_boundary_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan(
        "SV4_boundary_collection", "suspicious", "hard", "consolidation at an account whose outflow is unobserved"
    )
    hub = w.new_account()
    mules = w.accounts_n(r.randint(3, 9))
    t0 = _start_day(w, 8)
    for m in mules:
        p.txs.append(w.pay(m, hub, w.money(400_000, 0.5), t0 + r.uniform(0, 3)))
    w.scenario_boundary.add(hub)
    p.accounts = [hub, *mules]
    return p


def sv_recurring_mules(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("SV5_recurring_mule_collection", "suspicious", "adversarial", "mules imitate recurring customers")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(3, 8))
    exits = w.accounts_n(r.randint(1, 3))
    t0 = _start_day(w, 32)
    total, last = 0, t0
    for m in mules:
        for k in range(r.randint(2, 4)):
            a = w.money(220_000, 0.4)
            d = t0 + k * r.uniform(5, 9) + r.uniform(0, 1.5)
            last = max(last, d)
            p.txs.append(w.pay(m, hub, a, d))
            total += a
    for e in exits:
        p.txs.append(w.pay(hub, e, total * r.randint(70, 92) // 100 // len(exits), last + r.uniform(0.3, 4)))
    p.accounts = [hub, *mules, *exits]
    return p


def sv_slow_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("SV6_slow_collection", "suspicious", "hard", "deposits over 3-5 weeks, forwarded in tranches")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(6, 11))
    exit_acc = w.new_account()
    t0 = _start_day(w, 40)
    pending = 0
    events = sorted((t0 + r.uniform(0, r.uniform(21, 35)), m) for m in mules)
    for d, m in events:
        a = w.money(350_000, 0.5)
        p.txs.append(w.pay(m, hub, a, d))
        pending += a
        if pending > 1_200_000_00 and r.random() < 0.5:
            p.txs.append(w.pay(hub, exit_acc, pending * r.randint(80, 95) // 100, d + r.uniform(0.5, 6)))
            pending = 0
    if pending:
        p.txs.append(w.pay(hub, exit_acc, pending * r.randint(80, 95) // 100, events[-1][0] + r.uniform(0.5, 6)))
    p.accounts = [hub, *mules, exit_acc]
    return p


def sv_layering(w: _World) -> _Plan:
    r = w.rng
    hops = r.randint(3, 7)
    p = _Plan("SV7_layering_chain", "suspicious", "medium", f"{hops}-hop pass-through with fees and jitter")
    path = w.accounts_n(hops + 1)
    a = w.money(1_500_000, 0.7)
    d = _start_day(w, hops * 4 + 2)
    for i in range(hops):
        p.txs.append(w.pay(path[i], path[i + 1], a, d))
        a = a * r.randint(94, 99) // 100
        d += r.uniform(0.05, 4)
    p.accounts = path
    return p


def sv_partial_chain(w: _World) -> _Plan:
    r = w.rng
    hops = r.randint(4, 7)
    p = _Plan("SV8_partially_observed_chain", "suspicious", "hard", "one hop of a 4-7 hop chain is not in the data")
    path = w.accounts_n(hops + 1)
    missing = r.randrange(1, hops - 1)
    a = w.money(1_200_000, 0.6)
    d = _start_day(w, hops * 3 + 2)
    for i in range(hops):
        if i != missing:
            p.txs.append(w.pay(path[i], path[i + 1], a, d))
        a = a * r.randint(93, 99) // 100
        d += r.uniform(0.3, 2.5)
    p.accounts = path
    return p


def sv_distribution(w: _World) -> _Plan:
    r = w.rng
    terminal = r.random() < 0.3
    p = _Plan("SV9_mule_distribution", "suspicious", "hard" if terminal else "medium", "proceeds split across mules")
    src = w.accounts_n(r.randint(1, 2))
    hub = w.new_account()
    mules = w.accounts_n(r.randint(4, 14))
    exits = [] if terminal else w.accounts_n(r.randint(1, 4))
    t0 = _start_day(w, 14)
    total = 0
    for s in src:
        a = w.money(4_000_000, 0.5)
        p.txs.append(w.pay(s, hub, a, t0 + r.uniform(0, 1)))
        total += a
    dispersed = total * r.randint(75, 97) // 100
    for m in mules:
        part = dispersed // len(mules) * r.randint(70, 130) // 100
        d = t0 + r.uniform(1, 5)
        p.txs.append(w.pay(hub, m, part, d))
        if exits and r.random() < 0.8:
            p.txs.append(w.pay(m, r.choice(exits), part * r.randint(85, 98) // 100, d + r.uniform(0.1, 3)))
    p.accounts = [*src, hub, *mules, *exits]
    return p


def sv_round_trip(w: _World) -> _Plan:
    r = w.rng
    n = r.randint(3, 7)
    p = _Plan("SV10_round_trip", "suspicious", "medium", f"funds return to the origin through {n} accounts")
    ring = w.accounts_n(n)
    a = w.money(2_000_000, 0.6)
    d = _start_day(w, n * 3 * 3)
    for _ in range(r.choice((1, 2, 2, 3))):
        for i in range(n):
            p.txs.append(w.pay(ring[i], ring[(i + 1) % n], a, d))
            a = a * r.randint(96, 100) // 100
            d += r.uniform(0.2, 2.5)
    p.accounts = ring
    return p


def sv_salary_mule(w: _World) -> _Plan:
    """New: an account receives regular 'salary-like' deposits and forwards round sums at once."""
    r = w.rng
    p = _Plan("SV11_salary_pass_through", "suspicious", "adversarial", "weekly deposits forwarded in round amounts")
    mule = w.new_account()
    payers = w.accounts_n(r.randint(1, 2))
    exits = w.accounts_n(r.randint(1, 2))
    t0 = _start_day(w, 45)
    for week in range(r.randint(4, 7)):
        d = t0 + week * 7 + r.uniform(0, 1)
        a = w.money(600_000, 0.25)
        p.txs.append(w.pay(r.choice(payers), mule, a, d))
        p.txs.append(
            w.pay(mule, r.choice(exits), (a // 100 * r.randint(85, 98) // 100) // 10_000 * 10_000 * 100, d + 0.3)
        )
    p.accounts = [mule, *payers, *exits]
    return p


def sv_activation_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("SV12_activation_collection", "suspicious", "adversarial", "hub pays mules 3-20% first, then collects")
    hub = w.new_account()
    mules = w.accounts_n(r.randint(3, 9))
    exit_acc = w.new_account()
    t0 = _start_day(w, 18)
    total = 0
    for m in mules:
        a = w.money(380_000, 0.5)
        p.txs.append(w.pay(hub, m, a * r.randint(3, 20) // 100, t0 + r.uniform(0, 1)))
        p.txs.append(w.pay(m, hub, a, t0 + r.uniform(1.5, 5)))
        total += a
    p.txs.append(w.pay(hub, exit_acc, total * r.randint(65, 95) // 100, t0 + r.uniform(5.5, 10)))
    p.accounts = [hub, *mules, exit_acc]
    return p


# ----------------------------------------------------------------------------------------
# Legitimate families
# ----------------------------------------------------------------------------------------
def lv_rent_collection(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV1_rent_collection", "legitimate", "hard", "tenants pay monthly; landlord pays vendors and owner")
    landlord = w.new_account()
    tenants = w.accounts_n(r.randint(6, 24))
    vendors = w.accounts_n(r.randint(1, 5))
    owner = w.new_account()
    for month in (0, 30):
        collected = 0
        for t in tenants:
            a = w.money(260_000, 0.3)
            p.txs.append(w.pay(t, landlord, a, month + r.uniform(0, 6)))
            collected += a
        for v in vendors:
            p.txs.append(w.pay(landlord, v, w.money(250_000, 0.6), month + r.uniform(7, 14), business=True))
        p.txs.append(w.pay(landlord, owner, collected * r.randint(35, 75) // 100, month + r.uniform(10, 15)))
    p.accounts = [landlord, *tenants, *vendors, owner]
    return p


def lv_marketplace(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV2_marketplace_with_refunds", "legitimate", "hard", "platform settles sellers, refunds buyers")
    platform = w.new_account()
    buyers = w.accounts_n(r.randint(12, 35))
    sellers = w.accounts_n(r.randint(3, 9))
    settle_every = r.choice((1, 2, 3))
    pending = 0
    for day in range(WINDOW_DAYS):
        for b in buyers:
            if r.random() < 0.05:
                a = w.money(18_000, 0.8)
                p.txs.append(w.pay(b, platform, a, day + r.random()))
                pending += a
                if r.random() < 0.1:
                    p.txs.append(w.pay(platform, b, a, day + 1 + r.uniform(0, 4), business=True))
                    pending -= a
        if day % settle_every == 0 and pending > 0:
            for s in sellers:
                p.txs.append(w.pay(platform, s, pending * 94 // 100 // len(sellers), day + 0.8, business=True))
            pending = 0
    p.accounts = [platform, *buyers, *sellers]
    return p


def lv_payroll_spending(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV3_payroll_with_spending", "legitimate", "hard", "payroll whose recipients spend at shops")
    company = w.new_account()
    customers = w.accounts_n(r.randint(2, 7))
    staff = w.accounts_n(r.randint(5, 18))
    shops = w.accounts_n(r.randint(2, 7))
    for c in customers:
        for _ in range(r.randint(2, 5)):
            p.txs.append(w.pay(c, company, w.money(2_500_000, 0.5), r.uniform(0, WINDOW_DAYS), business=True))
    for payday in (r.uniform(4, 6), r.uniform(19, 21), r.uniform(34, 36), r.uniform(49, 51)):
        for s in staff:
            sal = w.money(420_000, 0.35)
            p.txs.append(w.pay(company, s, sal, payday, business=True))
            for _ in range(r.randint(0, 3)):
                p.txs.append(w.pay(s, r.choice(shops), sal * r.randint(3, 25) // 100, payday + r.uniform(0.1, 7)))
    p.accounts = [company, *customers, *staff, *shops]
    return p


def lv_remittance(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV4_family_remittance", "legitimate", "hard", "worker sends part of salary to relatives")
    employer = w.new_account()
    worker = w.new_account()
    relatives = w.accounts_n(r.randint(3, 9))
    for pay in (r.uniform(0, 5), r.uniform(29, 34)):
        salary = w.money(900_000, 0.3)
        p.txs.append(w.pay(employer, worker, salary, pay, business=True))
        for rel in relatives:
            if r.random() < 0.85:
                p.txs.append(w.pay(worker, rel, salary * r.randint(3, 14) // 100, pay + r.uniform(0, 3)))
    p.accounts = [employer, worker, *relatives]
    return p


def lv_cash_pooling(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV5_cash_pooling", "legitimate", "hard", "subsidiaries sweep balances to the parent")
    parent = w.new_account()
    subs = w.accounts_n(r.randint(2, 7))
    banks = w.accounts_n(r.randint(1, 3))
    clients_all: list[str] = []
    every = r.choice((7, 14))
    for s in subs:
        clients = w.accounts_n(r.randint(2, 6))
        clients_all.extend(clients)
        for c in clients:
            for _ in range(r.randint(2, 6)):
                p.txs.append(w.pay(c, s, w.money(800_000, 0.6), r.uniform(0, WINDOW_DAYS), business=True))
        for sweep in range(r.randrange(0, every), WINDOW_DAYS - 1, every):
            p.txs.append(w.pay(s, parent, w.money(2_500_000, 0.5), sweep + 0.7, business=True))
    for sweep in range(every - 1, WINDOW_DAYS - 1, every):
        p.txs.append(w.pay(parent, r.choice(banks), w.money(9_000_000, 0.5), sweep + 0.5, business=True))
    p.accounts = [parent, *subs, *banks, *clients_all]
    return p


def lv_lending(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV6_lending", "legitimate", "hard", "loans disbursed, instalments collected")
    lender = w.new_account()
    funder = w.new_account()
    borrowers = w.accounts_n(r.randint(4, 12))
    p.txs.append(w.pay(funder, lender, w.money(30_000_000, 0.3), 0.4, business=True))
    for b in borrowers:
        principal = w.money(1_200_000, 0.6)
        d = r.uniform(1, 10)
        p.txs.append(w.pay(lender, b, principal, d, business=True))
        k = 1
        while d + 14 * k < WINDOW_DAYS:
            p.txs.append(w.pay(b, lender, principal * r.randint(10, 25) // 100, d + 14 * k + r.uniform(-1, 1)))
            k += 1
    p.accounts = [lender, funder, *borrowers]
    return p


def lv_event_ticketing(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV7_event_ticketing", "legitimate", "adversarial", "one-off ticket buyers, payout to venue/artists")
    organiser = w.new_account()
    buyers = w.accounts_n(r.randint(5, 30))
    payees = w.accounts_n(r.randint(1, 4))
    t0 = _start_day(w, 16)
    total = 0
    for b in buyers:
        a = w.money(60_000, 0.6)
        p.txs.append(w.pay(b, organiser, a, t0 + r.uniform(0, 7)))
        total += a
    for v in payees:
        p.txs.append(
            w.pay(organiser, v, total * r.randint(55, 85) // 100 // len(payees), t0 + r.uniform(7, 12), business=True)
        )
    p.accounts = [organiser, *buyers, *payees]
    return p


def lv_charity(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV8_charity_campaign", "legitimate", "adversarial", "one-off donors, transfer to beneficiaries")
    fund = w.new_account()
    donors = w.accounts_n(r.randint(6, 30))
    beneficiaries = w.accounts_n(r.randint(1, 2))
    t0 = _start_day(w, 24)
    total = 0
    for dnr in donors:
        a = w.money(40_000, 0.9)
        p.txs.append(w.pay(dnr, fund, a, t0 + r.uniform(0, 14)))
        total += a
    for b in beneficiaries:
        p.txs.append(w.pay(fund, b, total * r.randint(80, 98) // 100 // len(beneficiaries), t0 + r.uniform(14, 22)))
    p.accounts = [fund, *donors, *beneficiaries]
    return p


def lv_supplier(w: _World) -> _Plan:
    r = w.rng
    p = _Plan("LV9_wholesale_supplier", "legitimate", "hard", "recurring customers, scheduled producer payments")
    firm = w.new_account()
    customers = w.accounts_n(r.randint(5, 16))
    producers = w.accounts_n(r.randint(3, 10))
    for c in customers:
        for _ in range(r.randint(2, 7)):
            p.txs.append(w.pay(c, firm, w.money(380_000, 0.6), r.uniform(0, WINDOW_DAYS), business=True))
    for cycle in range(r.randrange(8, 12), WINDOW_DAYS, 15):
        for pr in producers:
            p.txs.append(w.pay(firm, pr, w.money(600_000, 0.6), cycle + r.uniform(0, 2), business=True))
    p.accounts = [firm, *customers, *producers]
    return p


def lv_boundary_merchant(w: _World) -> _Plan:
    """New: a merchant collects from customers; its outflows are at another bank (declared boundary)."""
    r = w.rng
    p = _Plan("LV10_boundary_merchant", "legitimate", "hard", "customer payments to a merchant settled elsewhere")
    merchant = w.new_account()
    customers = w.accounts_n(r.randint(3, 10))
    t0 = _start_day(w, 10)
    for c in customers:
        p.txs.append(w.pay(c, merchant, w.money(150_000, 0.7), t0 + r.uniform(0, 6), business=True))
    w.scenario_boundary.add(merchant)
    p.accounts = [merchant, *customers]
    return p


def lv_property_escrow(w: _World) -> _Plan:
    """New: one large inbound, split within a day to seller, agent, tax and a bank (looks like distribution)."""
    r = w.rng
    p = _Plan("LV11_property_escrow", "legitimate", "adversarial", "escrow releases a sale to its parties")
    buyer = w.new_account()
    escrow = w.new_account()
    parties = w.accounts_n(r.randint(3, 6))
    d = _start_day(w, 4)
    price = w.round_money(30_000_000, 100_000)
    p.txs.append(w.pay(buyer, escrow, price, d, business=True))
    remaining = price
    for i, party in enumerate(parties):
        share = remaining if i == len(parties) - 1 else price * r.randint(2, 12) // 100
        remaining -= share
        p.txs.append(w.pay(escrow, party, share, d + r.uniform(0.2, 1.5), business=True))
    p.accounts = [buyer, escrow, *parties]
    return p


def lv_payroll_agency(w: _World) -> _Plan:
    """New: company → payroll agency → employees, monthly (a two-hop flow like a layering chain's start)."""
    r = w.rng
    p = _Plan("LV12_payroll_agency", "legitimate", "hard", "employer funds an agency that pays employees")
    company = w.new_account()
    agency = w.new_account()
    employees = w.accounts_n(r.randint(5, 16))
    for payday in (r.uniform(8, 10), r.uniform(38, 40)):
        salaries = [w.money(380_000, 0.3) for _ in employees]
        p.txs.append(w.pay(company, agency, sum(salaries) * r.randint(101, 104) // 100, payday - 1, business=True))
        for e, s in zip(employees, salaries, strict=True):
            p.txs.append(w.pay(agency, e, s, payday, business=True))
    p.accounts = [company, agency, *employees]
    return p


def lv_group_gift(w: _World) -> _Plan:
    """New: friends chip in small amounts and one of them pays a shop (like low-value coordination)."""
    r = w.rng
    p = _Plan("LV13_group_gift", "legitimate", "adversarial", "small contributions, then one purchase")
    organiser = w.new_account()
    friends = w.accounts_n(r.randint(5, 14))
    shop = w.new_account()
    t0 = _start_day(w, 6)
    total = 0
    for f in friends:
        a = w.round_money(5_000, 1_000)
        p.txs.append(w.pay(f, organiser, a, t0 + r.uniform(0, 2.5)))
        total += a
    p.txs.append(w.pay(organiser, shop, total * r.randint(90, 105) // 100, t0 + r.uniform(2.5, 5), business=True))
    p.accounts = [organiser, *friends, shop]
    return p


def _background(w: _World) -> None:
    r = w.rng
    people = w.accounts_n(r.randint(100, 220))
    for _ in range(r.randint(300, 800)):
        a, b = r.sample(people, 2)
        w.pay(a, b, w.money(25_000, 1.0, lo_tenge=200), r.uniform(0, WINDOW_DAYS), business=r.random() < 0.5)


SUSPICIOUS: list[tuple[str, int, Callable[[_World], _Plan]]] = [
    ("SV1_mule_collection", 3, sv_mule_collection),
    ("SV2_two_tier_collection", 2, sv_two_tier_collection),
    ("SV3_scatter_gather", 2, sv_scatter_gather),
    ("SV4_boundary_collection", 1, sv_boundary_collection),
    ("SV5_recurring_mule_collection", 1, sv_recurring_mules),
    ("SV6_slow_collection", 1, sv_slow_collection),
    ("SV7_layering_chain", 2, sv_layering),
    ("SV8_partially_observed_chain", 1, sv_partial_chain),
    ("SV9_mule_distribution", 2, sv_distribution),
    ("SV10_round_trip", 2, sv_round_trip),
    ("SV11_salary_pass_through", 1, sv_salary_mule),
    ("SV12_activation_collection", 1, sv_activation_collection),
]
LEGITIMATE: list[tuple[str, int, Callable[[_World], _Plan]]] = [
    ("LV1_rent_collection", 1, lv_rent_collection),
    ("LV2_marketplace_with_refunds", 1, lv_marketplace),
    ("LV3_payroll_with_spending", 1, lv_payroll_spending),
    ("LV4_family_remittance", 1, lv_remittance),
    ("LV5_cash_pooling", 1, lv_cash_pooling),
    ("LV6_lending", 1, lv_lending),
    ("LV7_event_ticketing", 1, lv_event_ticketing),
    ("LV8_charity_campaign", 1, lv_charity),
    ("LV9_wholesale_supplier", 1, lv_supplier),
    ("LV10_boundary_merchant", 1, lv_boundary_merchant),
    ("LV11_property_escrow", 1, lv_property_escrow),
    ("LV12_payroll_agency", 1, lv_payroll_agency),
    ("LV13_group_gift", 1, lv_group_gift),
]


def generate_sealed_v2(seed: int) -> GeneratedDataset:
    meta = random.Random(f"{SEALED_V2_GENERATOR_VERSION}|meta|{seed}")
    timestamped = meta.random() < 0.5
    w = _World(rng=random.Random(f"{SEALED_V2_GENERATOR_VERSION}|{seed}"), start=START, timestamped=timestamped)
    picks = [
        *w.rng.choices(SUSPICIOUS, weights=[x[1] for x in SUSPICIOUS], k=w.rng.randint(2, 5)),
        *w.rng.choices(LEGITIMATE, weights=[x[1] for x in LEGITIMATE], k=w.rng.randint(3, 7)),
    ]
    w.rng.shuffle(picks)
    truth: list[ScenarioTruth] = []
    for index, (_, _, build) in enumerate(picks):
        plan = build(w)
        # Truth lists exactly the accounts that occur in the scenario's transactions, in creation order (centre
        # first): an account a builder created but never used (a skipped relative, an unused exit) is not in the
        # data, so listing it would plant a positive no method could ever see.
        txs = set(plan.txs)
        used = {
            a
            for r in w.rows
            if r["source_transaction_id"] in txs
            for a in (r["sender_account_id"], r["receiver_account_id"])
        }
        plan.accounts = [a for a in plan.accounts if a in used]
        truth.append(
            ScenarioTruth(
                scenario_id=f"{SEALED_V2_SUITE}-{seed}-{index:02d}-{plan.family}",
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
    # Sampled from accounts present in the data, with `meta` (independent of labels and of scenario building).
    everyone = sorted({a for r in rows for a in (r["sender_account_id"], r["receiver_account_id"])})
    blind = {a for a in everyone if meta.random() < BOUNDARY_SAMPLE_RATE}
    contract = {
        "source": "synthetic",
        "generator_version": SEALED_V2_GENERATOR_VERSION,
        "time_precision": "timestamp" if timestamped else "day",
        "boundary_account_ids": sorted(blind | w.scenario_boundary),
        "upstream_observed": True,
        "declared_complete": False,
    }
    return GeneratedDataset(
        suite=SEALED_V2_SUITE,
        seed=seed,
        precision="timestamp" if timestamped else "day",
        rows=rows,
        coverage_contract=contract,
        truth=truth,
        window=(START, START + timedelta(days=WINDOW_DAYS - 1)),
    )
