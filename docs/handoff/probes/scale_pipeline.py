"""Scale probe for the pure analysis pipeline (no DB): time + peak RSS at N transfers.
Synthetic, skewed random graph with a few hubs; NOT representative of real data - it only shows
how cost grows with input size. Usage: scale_pipeline.py N"""

import random
import resource
import sys
import time
import uuid
from datetime import date, timedelta

from nexora.analytics.config import default_config
from nexora.analytics.pipeline import run_analysis
from nexora.domain.transfers import ObservedTransfer

n = int(sys.argv[1])
rng = random.Random(7)
n_acc = max(50, n // 5)
hubs = [f"H{i}" for i in range(20)]
accounts = [f"A{i}" for i in range(n_acc)]
d0 = date(2026, 7, 1)
tx = []
for i in range(n):
    r = rng.random()
    if r < 0.15:
        s, rcv = rng.choice(accounts), rng.choice(hubs)  # collection toward hubs
    elif r < 0.25:
        s, rcv = rng.choice(hubs), rng.choice(accounts)  # distribution from hubs
    else:
        s, rcv = rng.choice(accounts), rng.choice(accounts)
    if s == rcv:
        rcv = accounts[(accounts.index(rcv) + 1) % n_acc] if rcv in accounts else "A0"
    tx.append(
        ObservedTransfer(
            transaction_id=f"t{i}",
            source_transaction_id=f"s{i}",
            sender=s,
            receiver=rcv,
            amount_minor=rng.randint(10_000, 20_000_000),
            currency="KZT",
            observed_date=d0 + timedelta(days=rng.randint(0, 29)),
            occurred_at=None,
            precision="day",
        )
    )
rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
t = time.perf_counter()
out = run_analysis(
    dataset_id=str(uuid.uuid4()),
    transfers=tx,
    contract={"source": "scale-probe", "boundary_account_ids": []},
    config=default_config(),
)
dt = time.perf_counter() - t
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
print(
    f"N={n:>7} accounts={n_acc:>6} formations={len(out.formations):>5} seconds={dt:8.1f} "
    f"peak_rss_mib={rss:7.0f} (before analysis {rss0:.0f})",
    flush=True,
)
