"""Labelled benchmark scenario builders (benchmark ``nexora-bench-v1``).

Each benchmark *network* is one planted scenario embedded in its own independent background
population. Builders write canonical source rows only; ground truth is returned in a separate
``TruthRecord`` that never reaches detector input (ADR-009).

Design rules, fixed before any detector was tuned against this benchmark:

* Every family draws its size, amounts, timing, topology and noise from wide ranges, and most
  families have several variants. No family is a single planted example.
* Positive families have deliberately similar *benign* counterparts (hard negatives), several
  of which are indistinguishable from fraud using transaction data alone. They exist to measure
  honest uncertainty, not to be "solved".
* Account and transaction ids are random and carry no role information. Collection-boundary
  declarations occur in benign and suspicious networks alike, so the coverage contract does not
  leak the label.
* Amounts are integer tiyn; no floating-point value is ever written into a row.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

Label = Literal["suspicious", "benign"]
Difficulty = Literal["easy", "medium", "hard"]
#: Documented behaviour a careful analyst would want from the system for this instance.
Expected = Literal["detect", "ambiguous", "abstain", "no_alert", "lookalike"]

DAY_SECONDS = 86_400
OPEN_SECONDS = 8 * 3600
CLOSE_SECONDS = 21 * 3600


@dataclass(frozen=True)
class TruthRecord:
    network_id: str
    family: str
    variant: str
    label: Label
    difficulty: Difficulty
    expected: Expected
    accounts: tuple[str, ...]
    transaction_ids: tuple[str, ...]  # source transaction ids of the planted scenario
    notes: str


@dataclass(frozen=True)
class Stamp:
    tx_id: str
    day: int
    second: int  # seconds after local midnight; meaningful only for timestamp precision


@dataclass
class Net:
    """Mutable builder state for one network (scenario + background)."""

    rng: random.Random
    start: date
    days: int
    precision: Literal["day", "timestamp"]
    rows: list[dict[str, str]] = field(default_factory=list)
    used_accounts: set[str] = field(default_factory=set)
    used_tx: set[str] = field(default_factory=set)
    boundary: set[str] = field(default_factory=set)
    scenario_tx: list[str] = field(default_factory=list)
    recording: bool = True
    deferred: list[Callable[[Net, list[str]], None]] = field(default_factory=list)

    # -- identities --------------------------------------------------------------------
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

    def accounts(self, n: int) -> list[str]:
        return [self.account() for _ in range(n)]

    # -- transfers ---------------------------------------------------------------------
    def tx(
        self,
        sender: str,
        receiver: str,
        amount_minor: int,
        day: int,
        *,
        after: Stamp | None = None,
    ) -> Stamp:
        """Record one posted transfer. ``after`` forces a strictly later instant on the same day."""
        if amount_minor <= 0:
            raise ValueError("amount must be positive")
        day = max(0, min(self.days - 1, day))
        if after is not None and day == after.day:
            lo = min(after.second + 120, CLOSE_SECONDS + 3000)
            second = self.rng.randrange(lo, max(lo + 1, CLOSE_SECONDS + 3600))
        else:
            second = self.rng.randrange(OPEN_SECONDS, CLOSE_SECONDS)
        while True:
            tx_id = f"{self.rng.getrandbits(64):016x}"
            if tx_id not in self.used_tx:
                self.used_tx.add(tx_id)
                break
        d = self.start + timedelta(days=day)
        occurred = ""
        if self.precision == "timestamp":
            ts = datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(seconds=min(second, DAY_SECONDS - 1))
            occurred = ts.isoformat().replace("+00:00", "Z")
        self.rows.append(
            {
                "source_transaction_id": tx_id,
                "sender_account_id": sender,
                "receiver_account_id": receiver,
                "amount_minor": str(amount_minor),
                "currency": "KZT",
                "observed_date": d.isoformat(),
                "occurred_at": occurred,
                "status": "posted",
            }
        )
        if self.recording:
            self.scenario_tx.append(tx_id)
        return Stamp(tx_id, day, second)

    # -- random helpers ------------------------------------------------------------------
    def kzt(self, lo: int, hi: int) -> int:
        """Log-uniform amount between ``lo`` and ``hi`` whole tenge, returned in tiyn."""
        whole = int(math.exp(self.rng.uniform(math.log(lo), math.log(hi))))
        return max(1, whole) * 100 + self.rng.randrange(100)

    def part(self, amount: int, lo_bp: int, hi_bp: int) -> int:
        """``amount`` scaled by a random ratio in basis points (integer arithmetic)."""
        return max(1, amount * self.rng.randint(lo_bp, hi_bp) // 10_000)

    def split(self, amount: int, n: int, jitter_bp: int = 2500) -> list[int]:
        """Split ``amount`` into ``n`` positive integer parts that sum exactly to ``amount``."""
        weights = [10_000 + self.rng.randint(-jitter_bp, jitter_bp) for _ in range(n)]
        total = sum(weights)
        parts = [max(1, amount * w // total) for w in weights[:-1]]
        parts.append(max(1, amount - sum(parts)))
        return parts

    def pick(self, options: list[tuple[str, float]]) -> str:
        r = self.rng.random() * sum(w for _, w in options)
        for name, w in options:
            r -= w
            if r <= 0:
                return name
        return options[-1][0]

    def lag(self, weights: tuple[float, ...]) -> int:
        """Day lag drawn from weights indexed by lag 0, 1, 2, …"""
        r = self.rng.random() * sum(weights)
        for i, w in enumerate(weights):
            r -= w
            if r <= 0:
                return i
        return len(weights) - 1

    def defer(self, fn: Callable[[Net, list[str]], None]) -> None:
        """Run ``fn(net, background_accounts)`` once the background population exists."""
        self.deferred.append(fn)


# ---------------------------------------------------------------------------------------
# shared behaviours
# ---------------------------------------------------------------------------------------


def _spend_gradually(accounts: list[str], *, n: tuple[int, int], lo: int, hi: int, from_day: int = 0) -> Callable:
    """Deferred behaviour: each account makes small payments to background accounts over time."""

    def run(net: Net, bg: list[str]) -> None:
        for acc in accounts:
            for _ in range(net.rng.randint(*n)):
                day = net.rng.randrange(min(from_day, net.days - 1), net.days)
                net.tx(acc, net.rng.choice(bg), net.kzt(lo, hi), day)

    return run


def _incidental(accounts: list[str], *, count: tuple[int, int], lo: int, hi: int) -> Callable:
    """Deferred behaviour: unrelated transfers in either direction with background accounts."""

    def run(net: Net, bg: list[str]) -> None:
        for acc in accounts:
            for _ in range(net.rng.randint(*count)):
                other = net.rng.choice(bg)
                day = net.rng.randrange(net.days)
                if net.rng.random() < 0.5:
                    net.tx(acc, other, net.kzt(lo, hi), day)
                else:
                    net.tx(other, acc, net.kzt(lo, hi), day)

    return run


# ---------------------------------------------------------------------------------------
# suspicious families
# ---------------------------------------------------------------------------------------


def p1_mule_collection(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Several feeders consolidate into one account which forwards most of the funds onwards."""
    variant = net.pick([("standard", 0.35), ("large", 0.15), ("slow", 0.15), ("repeated", 0.15), ("boundary", 0.2)])
    centre = net.account()
    exits = net.accounts(net.rng.randint(1, 3))
    feeders_all: list[str] = []
    episodes = net.rng.randint(2, 3) if variant == "repeated" else 1
    episode_len = 9
    day0 = net.rng.randrange(1, max(2, net.days - episodes * episode_len - 6))
    for ep in range(episodes):
        if variant == "large":
            n_feed, lo, hi, span = net.rng.randint(9, 20), 20_000, 400_000, net.rng.randint(0, 6)
        elif variant == "slow":
            n_feed, lo, hi, span = net.rng.randint(4, 9), 60_000, 1_200_000, net.rng.randint(8, 16)
        elif variant == "repeated":
            n_feed, lo, hi, span = net.rng.randint(3, 6), 80_000, 1_000_000, net.rng.randint(0, 3)
        else:
            n_feed, lo, hi, span = net.rng.randint(3, 8), 80_000, 1_500_000, net.rng.randint(0, 4)
        start = day0 + ep * episode_len
        span = min(span, max(0, net.days - start - 5))
        feeders = net.accounts(n_feed)
        feeders_all.extend(feeders)
        arrivals: list[tuple[Stamp, int]] = []
        for f in feeders:
            for _ in range(2 if net.rng.random() < 0.2 else 1):
                amount = net.kzt(lo, hi)
                arrivals.append((net.tx(f, centre, amount, start + net.rng.randint(0, span)), amount))
        if variant == "boundary":
            continue
        arrivals.sort(key=lambda a: (a[0].day, a[0].second))
        batches = [arrivals]
        if variant == "slow" and len(arrivals) >= 4:
            cut = sorted(net.rng.sample(range(1, len(arrivals)), k=min(2, len(arrivals) - 1)))
            batches = [arrivals[i:j] for i, j in zip([0, *cut], [*cut, len(arrivals)], strict=True)]
        for batch in batches:
            last = batch[-1][0]
            total = net.part(sum(a for _, a in batch), 7_500, 9_800)
            for exit_acc, share in zip(exits, net.split(total, len(exits), 4000), strict=True):
                day = last.day + net.lag((0.2, 0.35, 0.25, 0.2))
                pieces = net.split(share, net.rng.randint(1, 2), 3000)
                prev = last
                for piece in pieces:
                    prev = net.tx(centre, exit_acc, piece, day, after=prev if day == prev.day else None)
    if variant == "boundary":
        net.boundary.add(centre)
    net.defer(_incidental(feeders_all, count=(0, 2), lo=1_000, hi=60_000))
    net.defer(_incidental([centre, *exits], count=(0, 2), lo=1_000, hi=40_000))
    accounts = [*feeders_all, centre, *([] if variant == "boundary" else exits)]
    difficulty: Difficulty = {"standard": "easy", "boundary": "hard"}.get(variant, "medium")  # type: ignore[assignment]
    expected: Expected = "abstain" if variant == "boundary" else "detect"
    return variant, difficulty, expected, accounts, "consolidation then onward transfer"


def p2_layering_chain(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Funds hop through several pass-through accounts, losing a small 'fee' at each hop."""
    variant = net.pick([("clean", 0.3), ("noisy", 0.3), ("split", 0.2), ("same_day", 0.2)])
    if variant == "same_day":
        net.precision = "day"
    hops = net.rng.randint(3, 6)
    path = net.accounts(hops + 1)
    amount = net.kzt(300_000, 5_000_000)
    day = net.rng.randrange(0, max(1, net.days - 3 * hops - 1))
    split_hop = net.rng.randrange(hops) if variant == "split" else -1
    prev: Stamp | None = None
    for i in range(hops):
        if i > 0 and variant != "same_day":
            day += net.lag((0.15, 0.4, 0.3, 0.15))
        parts = net.split(amount, net.rng.randint(2, 3), 3000) if i == split_hop else [amount]
        last: Stamp | None = None
        for piece in parts:
            ref = last or prev
            last = net.tx(path[i], path[i + 1], piece, day, after=ref if ref and ref.day == day else None)
        prev = last
        amount = net.part(amount, 9_000, 9_950)
    if variant == "noisy":
        net.defer(_incidental(path[1:-1], count=(1, 4), lo=2_000, hi=150_000))
    net.defer(_incidental([path[0], path[-1]], count=(0, 2), lo=1_000, hi=60_000))
    difficulty: Difficulty = {"clean": "easy", "same_day": "hard"}.get(variant, "medium")  # type: ignore[assignment]
    expected: Expected = "ambiguous" if variant == "same_day" else "detect"
    return variant, difficulty, expected, path, f"{hops}-hop pass-through"


def p3_coordinated_distribution(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """A funded source disperses quickly to many recipients who forward almost everything on."""
    variant = net.pick([("converge", 0.4), ("scatter", 0.35), ("boundary", 0.25)])
    source = net.account()
    funders = net.accounts(net.rng.randint(1, 2))
    total = net.kzt(1_000_000, 15_000_000)
    day0 = net.rng.randrange(0, max(1, net.days - 9))
    last: Stamp | None = None
    for funder, piece in zip(funders, net.split(total, len(funders)), strict=True):
        s = net.tx(funder, source, piece, day0 + net.rng.randint(0, 1))
        last = s if last is None or (s.day, s.second) > (last.day, last.second) else last
    assert last is not None
    recipients = net.accounts(net.rng.randint(5, 14))
    exits = net.accounts(net.rng.randint(1, 3)) if variant == "converge" else []
    disperse_day = last.day + net.lag((0.3, 0.45, 0.25))
    dispersed = net.part(total, 8_500, 9_800)
    for r, amount in zip(recipients, net.split(dispersed, len(recipients)), strict=True):
        got = net.tx(source, r, amount, disperse_day, after=last if disperse_day == last.day else None)
        if variant == "boundary":
            net.boundary.add(r)
            continue
        target = net.rng.choice(exits) if variant == "converge" else net.account()
        if variant == "scatter":
            exits.append(target)
        fwd_day = got.day + net.lag((0.25, 0.4, 0.25, 0.1))
        net.tx(r, target, net.part(amount, 8_500, 9_800), fwd_day, after=got if fwd_day == got.day else None)
    net.defer(_incidental([source, *funders], count=(0, 2), lo=1_000, hi=60_000))
    difficulty: Difficulty = {"converge": "easy", "scatter": "medium"}.get(variant, "hard")  # type: ignore[assignment]
    expected: Expected = "abstain" if variant == "boundary" else "detect"
    return variant, difficulty, expected, [*funders, source, *recipients, *exits], "rapid fan-out then onward"


def p4_circular_transfers(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """The same value travels around a small cycle of accounts several times."""
    variant = net.pick([("clean", 0.5), ("noisy", 0.5)])
    length = net.rng.choice([2, 3, 3, 4, 4, 5])
    members = net.accounts(length)
    rounds_target = net.rng.randint(2, 5)
    max_leg_lag = 2 if length >= 4 else 3
    day = net.rng.randrange(0, 4)
    base = net.kzt(200_000, 3_000_000)
    rounds = 0
    while rounds < rounds_target and day + length * max_leg_lag < net.days:
        amount = net.part(base, 7_000, 13_000)
        prev: Stamp | None = None
        for leg in range(length):
            if leg > 0:
                day += net.lag((0.15, 0.5, 0.35)[: max_leg_lag + 1])
            prev = net.tx(
                members[leg],
                members[(leg + 1) % length],
                amount,
                day,
                after=prev if prev and prev.day == day else None,
            )
            amount = net.part(amount, 9_700, 10_000)
        rounds += 1
        day += net.rng.randint(2, 7)
    if variant == "noisy":
        net.defer(_incidental(members, count=(1, 4), lo=2_000, hi=200_000))
    difficulty: Difficulty = "easy" if variant == "clean" else "medium"
    return variant, difficulty, "detect", members, f"{length}-account cycle x{rounds}"


def p5_split_coordinated(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Large sums are split below a reporting threshold across smurf accounts and re-consolidated."""
    variant = net.pick([("single_source", 0.5), ("multi_source", 0.5)])
    threshold = net.rng.choice([1_000_000, 2_000_000, 5_000_000]) * 100
    sources = net.accounts(1 if variant == "single_source" else net.rng.randint(2, 3))
    smurfs = net.accounts(net.rng.randint(4, 10))
    collectors = net.accounts(net.rng.randint(1, 2))
    day0 = net.rng.randrange(0, max(1, net.days - 8))
    received: dict[str, list[tuple[Stamp, int]]] = {s: [] for s in smurfs}
    for src in sources:
        n_pieces = net.rng.randint(len(smurfs), 2 * len(smurfs))
        for i in range(n_pieces):
            piece = threshold * net.rng.randint(6_000, 9_900) // 10_000
            smurf = smurfs[i % len(smurfs)]
            received[smurf].append((net.tx(src, smurf, piece, day0 + net.rng.randint(0, 2)), piece))
    for smurf, got in received.items():
        if not got:
            continue
        last = max((s for s, _ in got), key=lambda s: (s.day, s.second))
        total = net.part(sum(a for _, a in got), 9_500, 10_000)
        day = last.day + net.lag((0.35, 0.45, 0.2))
        n = max(1, -(-total // (threshold * 9 // 10)))  # keep each forwarded piece below the threshold
        prev = last
        for piece in net.split(total, n, 1500):
            prev = net.tx(smurf, net.rng.choice(collectors), piece, day, after=prev if prev.day == day else None)
    net.defer(_incidental([*sources, *collectors], count=(0, 2), lo=1_000, hi=80_000))
    return variant, "medium", "detect", [*sources, *smurfs, *collectors], "split below threshold and re-consolidate"


# ---------------------------------------------------------------------------------------
# benign families
# ---------------------------------------------------------------------------------------


def n1_merchant_settlement(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Customers pay a processor that settles to its merchants on a fixed cadence."""
    variant = net.pick([("standard", 0.55), ("bursty", 0.25), ("small", 0.2)])
    processor = net.account()
    n_cust = {"standard": (15, 80), "bursty": (15, 60), "small": (4, 9)}[variant]
    customers = net.accounts(net.rng.randint(*n_cust))
    merchants = net.accounts(net.rng.randint(2, 4) if variant == "small" else net.rng.randint(3, 12))
    weights = [net.rng.randint(1, 10) for _ in merchants]
    cadence = net.rng.choice([1, 2, 3, 5, 7])
    offset = net.rng.randrange(cadence)
    fee_bp = net.rng.randint(9_600, 9_950)
    event = (net.rng.randrange(0, max(1, net.days - 6)), net.rng.randint(3, 6))
    lo, hi = (20_000, 300_000) if variant == "small" else (3_000, 60_000)
    base_rate = {c: net.rng.uniform(0.03, 0.2) for c in customers}
    pending = 0
    for day in range(net.days):
        for c in customers:
            if variant == "bursty":
                rate = 0.6 if event[0] <= day < event[0] + event[1] else 0.02
            elif variant == "small":
                rate = 0.25
            else:
                rate = base_rate[c]
            if net.rng.random() < rate:
                amount = net.kzt(lo, hi)
                net.tx(c, processor, amount, day)
                pending += amount
        if day % cadence == offset and pending > 0:
            payout = pending * fee_bp // 10_000
            for m, share in zip(merchants, _weighted(payout, weights), strict=True):
                if share > 0:
                    net.tx(processor, m, share, day)
            pending = 0
    net.defer(_spend_gradually(customers, n=(0, 3), lo=1_000, hi=50_000))
    net.defer(_spend_gradually(merchants, n=(1, 4), lo=10_000, hi=500_000))
    difficulty: Difficulty = "hard" if variant == "small" else "medium"
    return variant, difficulty, "no_alert", [processor, *customers, *merchants], f"settles every {cadence} d"


def n2_payroll(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """An employer funded by client payments pays salaries; employees then spend them."""
    variant = net.pick([("monthly", 0.6), ("biweekly", 0.4)])
    employer = net.account()
    clients = net.accounts(net.rng.randint(1, 3))
    employees = net.accounts(net.rng.randint(6, 40))
    salaries = {e: net.kzt(150_000, 900_000) for e in employees}
    paydays = (
        [net.rng.randint(net.days // 2, net.days - 3)]
        if variant == "monthly"
        else [d for d in (net.rng.randint(5, 10), net.rng.randint(19, 24)) if d < net.days - 2]
    )
    payroll = sum(salaries.values()) * len(paydays)
    funding = payroll * net.rng.randint(10_000, 16_000) // 10_000
    for client, piece in zip(clients, net.split(funding, len(clients)), strict=True):
        net.tx(client, employer, piece, net.rng.randint(0, max(0, paydays[0] - 2)))
    family: list[str] = []
    for payday in paydays:
        for e in employees:
            paid = net.tx(employer, e, salaries[e], payday)
            if net.rng.random() < 0.25:
                relative = net.account()
                family.append(relative)
                day = payday + net.lag((0.3, 0.4, 0.2, 0.1))
                net.tx(e, relative, net.part(salaries[e], 1_000, 3_000), day, after=paid if day == payday else None)
    net.defer(_spend_gradually(employees, n=(2, 8), lo=1_000, hi=40_000, from_day=min(paydays)))
    net.defer(_incidental(clients, count=(1, 3), lo=50_000, hi=2_000_000))
    return variant, "medium", "no_alert", [employer, *clients, *employees, *family], f"{len(employees)} employees"


def n3_supplier_payments(net: Net, *, tight: bool = False) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Buyer → distributor → manufacturer → raw supplier, each keeping a trade margin."""
    buyers = net.accounts(1 if tight else net.rng.randint(1, 3))
    distributor = net.account()
    manufacturers = net.accounts(1 if tight else net.rng.randint(1, 2))
    raw = net.accounts(1 if tight else net.rng.randint(1, 2))
    orders = net.rng.randint(1, 2) if tight else net.rng.randint(2, 4)
    margin = (9_200, 9_850) if tight else (7_000, 9_000)
    lag = (0.25, 0.4, 0.25, 0.1) if tight else tuple([0.0, 0.0, 0.0] + [1.0] * 12)
    for _ in range(orders):
        day = net.rng.randrange(0, max(1, net.days - (8 if tight else 20)))
        value = net.kzt(500_000, 8_000_000)
        s = net.tx(net.rng.choice(buyers), distributor, value, day)
        value = net.part(value, *margin)
        day = s.day + net.lag(lag)
        s = net.tx(distributor, net.rng.choice(manufacturers), value, day, after=s if day == s.day else None)
        value = net.part(value, *margin) if tight else net.part(value, 4_000, 7_000)
        day = s.day + net.lag(lag)
        net.tx(net.rng.choice(manufacturers), net.rng.choice(raw), value, day, after=s if day == s.day else None)
    net.defer(_incidental([*buyers, distributor, *manufacturers, *raw], count=(1, 4), lo=10_000, hi=800_000))
    accounts = [*buyers, distributor, *manufacturers, *raw]
    if tight:
        return "tight", "hard", "lookalike", accounts, "low-margin same-week supply chain"
    return "standard", "medium", "no_alert", accounts, f"{orders} orders"


def n4_family_remittance(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """A worker supports relatives, or siblings pool money for a parent who spends it."""
    variant = net.pick([("support", 0.7), ("pooling", 0.3)])
    if variant == "support":
        worker = net.account()
        employer = net.account()
        family = net.accounts(net.rng.randint(2, 6))
        for _ in range(net.rng.randint(1, 2)):
            day = net.rng.randrange(0, max(1, net.days - 6))
            salary = net.kzt(200_000, 1_200_000)
            paid = net.tx(employer, worker, salary, day)
            for f in family:
                d = paid.day + net.lag((0.2, 0.3, 0.2, 0.15, 0.1, 0.05))
                net.tx(worker, f, net.part(salary, 1_000, 3_000), d, after=paid if d == paid.day else None)
        net.defer(_spend_gradually(family, n=(2, 6), lo=1_000, hi=30_000))
        net.defer(_spend_gradually([worker], n=(3, 8), lo=1_000, hi=40_000))
        return variant, "easy", "no_alert", [employer, worker, *family], "monthly support"
    parent = net.account()
    siblings = net.accounts(net.rng.randint(3, 6))
    for _ in range(net.rng.randint(1, 2)):
        day = net.rng.randrange(0, max(1, net.days - 8))
        got: list[tuple[Stamp, int]] = []
        for s in siblings:
            amount = net.kzt(20_000, 200_000)
            got.append((net.tx(s, parent, amount, day + net.rng.randint(0, 3)), amount))
        if net.rng.random() < 0.5:
            last = max((g for g, _ in got), key=lambda s: (s.day, s.second))
            d = last.day + net.rng.randint(1, 6)
            net.tx(parent, net.account(), net.part(sum(a for _, a in got), 4_000, 8_000), d)
    net.defer(_spend_gradually([parent], n=(3, 10), lo=1_000, hi=30_000))
    return variant, "medium", "no_alert", [parent, *siblings], "siblings pool for a parent"


def n5_group_reimbursement(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """A friend pays a venue up front; the others reimburse their share afterwards."""
    friends = net.accounts(net.rng.randint(3, 8))
    for _ in range(net.rng.randint(2, 6)):
        payer = net.rng.choice(friends)
        day = net.rng.randrange(0, max(1, net.days - 6))
        total = net.kzt(20_000, 400_000)
        paid = net.tx(payer, net.account(), total, day)
        share = total // len(friends)
        for f in friends:
            if f != payer:
                d = paid.day + net.lag((0.3, 0.25, 0.2, 0.1, 0.1, 0.05))
                net.tx(f, payer, share, d, after=paid if d == paid.day else None)
    return "standard", "easy", "no_alert", friends, "split bills"


def n6_loan_repayment(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Personal or family loans repaid in regular instalments with interest."""
    variant = net.pick([("personal", 0.6), ("family_lending", 0.4)])
    lender = net.account()
    borrowers = net.accounts(1 if variant == "personal" else net.rng.randint(2, 3))
    for b in borrowers:
        loan = net.kzt(100_000, 3_000_000)
        day = net.rng.randint(0, 5)
        net.tx(lender, b, loan, day)
        n = net.rng.randint(3, 8)
        step = net.rng.choice([3, 5, 7])
        instalment = loan * net.rng.randint(10_100, 11_500) // 10_000 // n
        for i in range(n):
            d = day + step * (i + 1)
            if d >= net.days:
                break
            net.tx(b, lender, instalment, d)
    net.defer(_spend_gradually([lender, *borrowers], n=(1, 4), lo=1_000, hi=60_000))
    return variant, "easy", "no_alert", [lender, *borrowers], "instalment repayments"


# ---------------------------------------------------------------------------------------
# hard negatives (benign by construction, deliberately similar to fraud)
# ---------------------------------------------------------------------------------------


def h1_crowdfunding(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Donors (or trip members) pay an organiser in a burst; the organiser pays one beneficiary."""
    variant = net.pick([("crowdfunding", 0.6), ("group_purchase", 0.4)])
    organiser = net.account()
    n = (6, 40) if variant == "crowdfunding" else (3, 9)
    donors = net.accounts(net.rng.randint(*n))
    beneficiaries = net.accounts(net.rng.randint(1, 2))
    day0 = net.rng.randrange(0, max(1, net.days - 10))
    span = net.rng.randint(1, 5)
    lo, hi = (2_000, 200_000) if variant == "crowdfunding" else (50_000, 500_000)
    got = [(net.tx(d, organiser, (a := net.kzt(lo, hi)), day0 + net.rng.randint(0, span)), a) for d in donors]
    last = max((g for g, _ in got), key=lambda s: (s.day, s.second))
    total = net.part(sum(a for _, a in got), 8_500, 10_000)
    for b, piece in zip(beneficiaries, net.split(total, len(beneficiaries)), strict=True):
        d = last.day + net.lag((0.15, 0.35, 0.3, 0.15, 0.05))
        net.tx(organiser, b, piece, d, after=last if d == last.day else None)
    net.defer(_spend_gradually(donors, n=(0, 3), lo=1_000, hi=40_000))
    return variant, "hard", "lookalike", [*donors, organiser, *beneficiaries], "legitimate collection then payment"


def h2_microfinance_hub(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """A lender collects instalments and promptly re-lends them to new borrowers."""
    lender = net.account()
    investor = net.account()
    borrowers = net.accounts(net.rng.randint(6, 25))
    capital = net.kzt(2_000_000, 20_000_000)
    net.tx(investor, lender, capital, 0)
    cohorts = [borrowers[: len(borrowers) // 2], borrowers[len(borrowers) // 2 :]]
    loans: dict[str, tuple[int, int]] = {}
    for b in cohorts[0]:
        day = net.rng.randint(1, 4)
        loan = net.kzt(50_000, 600_000)
        net.tx(lender, b, loan, day)
        loans[b] = (day, loan)
    step = net.rng.choice([5, 7])
    collected_by_day: dict[int, int] = {}
    for b, (day, loan) in list(loans.items()):
        instalment = loan * net.rng.randint(10_500, 12_500) // 10_000 // 4
        for i in range(4):
            d = day + step * (i + 1)
            if d < net.days:
                net.tx(b, lender, instalment, d)
                collected_by_day[d] = collected_by_day.get(d, 0) + instalment
    pending = 0
    later = list(cohorts[1])
    for d in range(net.days):
        pending += collected_by_day.get(d, 0)
        if later and pending > 50_000 * 100:
            b = later.pop(0)
            lend_day = min(net.days - 1, d + net.rng.randint(0, 3))
            loan = net.part(pending, 6_000, 9_500)
            net.tx(lender, b, loan, lend_day)
            pending -= loan
            instalment = loan * 11_000 // 10_000 // 4
            for i in range(4):
                rd = lend_day + step * (i + 1)
                if rd < net.days:
                    net.tx(b, lender, instalment, rd)
    net.defer(_spend_gradually(borrowers, n=(1, 4), lo=1_000, hi=40_000))
    return "standard", "hard", "lookalike", [investor, lender, *borrowers], "instalments recycled into new loans"


def h3_tight_supplier_chain(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    return n3_supplier_payments(net, tight=True)


def h4_reverse_chronology_chain(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """A path with layering-like amounts whose later legs happen before the earlier ones."""
    hops = net.rng.randint(3, 5)
    path = net.accounts(hops + 1)
    amount = net.kzt(300_000, 5_000_000)
    days = sorted(net.rng.sample(range(net.days), hops), reverse=True)
    for i in range(hops):
        net.tx(path[i], path[i + 1], amount, days[i])
        amount = net.part(amount, 9_000, 9_950)
    net.defer(_incidental(path, count=(0, 2), lo=1_000, hi=60_000))
    return "standard", "hard", "no_alert", path, "unrelated transfers that happen to form a path backwards in time"


def h5_payout_sweep(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """A platform pays gig workers, who immediately sweep most of it to their own savings."""
    platform = net.account()
    clients = net.accounts(net.rng.randint(1, 3))
    workers = net.accounts(net.rng.randint(6, 20))
    savings = [net.account() for _ in workers]
    pay = {w: net.kzt(60_000, 500_000) for w in workers}
    payday = net.rng.randrange(4, max(5, net.days - 4))
    for c, piece in zip(clients, net.split(sum(pay.values()) * 11 // 10, len(clients)), strict=True):
        net.tx(c, platform, piece, net.rng.randint(0, payday - 1))
    for w, s in zip(workers, savings, strict=True):
        paid = net.tx(platform, w, pay[w], payday)
        d = payday + net.lag((0.45, 0.4, 0.15))
        net.tx(w, s, net.part(pay[w], 7_000, 9_500), d, after=paid if d == payday else None)
    net.defer(_spend_gradually(workers, n=(1, 4), lo=1_000, hi=20_000))
    return "standard", "hard", "lookalike", [platform, *clients, *workers, *savings], "salary swept to savings"


def h6_reciprocal_trading(net: Net) -> tuple[str, Difficulty, Expected, list[str], str]:
    """Businesses invoice each other around a ring with independent amounts and dates."""
    size = net.rng.randint(2, 4)
    firms = net.accounts(size)
    for i in range(size):
        a, b = firms[i], firms[(i + 1) % size]
        for _ in range(net.rng.randint(3, 8)):
            net.tx(a, b, net.kzt(100_000, 2_000_000), net.rng.randrange(net.days))
    net.defer(_incidental(firms, count=(1, 4), lo=10_000, hi=500_000))
    return "standard", "hard", "no_alert", firms, "independent mutual invoicing"


def _weighted(amount: int, weights: list[int]) -> list[int]:
    total = sum(weights)
    parts = [amount * w // total for w in weights[:-1]]
    parts.append(amount - sum(parts))
    return parts


# ---------------------------------------------------------------------------------------
# background population
# ---------------------------------------------------------------------------------------


def background(net: Net, *, n_accounts: int, n_transfers: int) -> list[str]:
    """Unlabelled activity with popular receivers ("shops") that periodically pay suppliers.

    May contain coincidental structures, as real data does. Never recorded as scenario truth.
    """
    accounts = net.accounts(n_accounts)
    n_shops = max(2, n_accounts // 15)
    shops, people = accounts[:n_shops], accounts[n_shops:]
    receivers = [*shops * 8, *people]
    takings: dict[str, int] = dict.fromkeys(shops, 0)
    per_day = [0] * net.days
    for _ in range(n_transfers):
        per_day[net.rng.randrange(net.days)] += 1
    supplier = {s: net.rng.choice(people) for s in shops}
    for day, count in enumerate(per_day):
        for _ in range(count):
            sender = net.rng.choice(people)
            receiver = net.rng.choice(receivers)
            if receiver == sender:
                continue
            amount = net.kzt(500, 150_000)
            net.tx(sender, receiver, amount, day)
            if receiver in takings:
                takings[receiver] += amount
        if day % 7 == 6:
            for s in shops:
                if takings[s] > 0 and net.rng.random() < 0.7:
                    net.tx(s, supplier[s], net.part(takings[s], 2_000, 5_000), day)
                    takings[s] = 0
    return accounts
