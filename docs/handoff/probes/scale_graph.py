"""Probe: cost of graph_view.bfs_neighborhood against PostgreSQL when a hub has many counterparties.
Seeds a throw-away dataset in the DEV database, measures, then deletes it.
Usage: scale_graph.py HUB_PEERS BACKGROUND_TRANSFERS   (e.g. 20000 160000)"""

import datetime as dt
import os
import random
import sys
import time
import uuid
from types import SimpleNamespace

from sqlalchemy import create_engine, delete, insert, text
from sqlalchemy.orm import sessionmaker

from nexora.application import graph_view
from nexora.persistence import orm

# A DEVELOPMENT database only (the probe seeds and then deletes its own throw-away dataset).
URL = os.environ.get("NEXORA_PROBE_DATABASE_URL", "postgresql+psycopg://nexora:nexora@localhost:5432/nexora")
eng = create_engine(URL)
S = sessionmaker(bind=eng, expire_on_commit=False)
rng = random.Random(3)
ds_id, batch_id = uuid.uuid4(), uuid.uuid4()
HUB_PEERS, BACKGROUND = int(sys.argv[1]), int(sys.argv[2])
d0 = dt.date(2026, 7, 1)


def row(i, s, r):
    return dict(
        id=uuid.uuid4(),
        dataset_id=ds_id,
        import_batch_id=batch_id,
        source_id="probe",
        source_transaction_id=f"p{i}",
        sender_account_id=s,
        receiver_account_id=r,
        amount_minor=rng.randint(10_000, 9_000_000),
        currency="KZT",
        occurred_at=None,
        observed_date=d0 + dt.timedelta(days=rng.randint(0, 29)),
        time_precision="day",
        status="posted",
        is_synthetic=True,
        raw_record_hash="0" * 64,
    )


try:
    with S() as s:
        s.add(
            orm.Dataset(
                id=ds_id, name="scale-probe", source_kind="synthetic", time_precision="day", coverage_contract={}
            )
        )
        s.flush()
        s.add(
            orm.ImportBatch(
                id=batch_id,
                dataset_id=ds_id,
                content_sha256="0" * 64,
                accepted=0,
                duplicate=0,
                quarantined=0,
                rejected=0,
                report={},
                status="completed",
            )
        )
        s.flush()
        rows, i = [], 0
        for p in range(HUB_PEERS):  # hub <-> each peer, both directions
            rows.append(row(i, f"P{p}", "HUB"))
            i += 1
            rows.append(row(i, "HUB", f"P{p}"))
            i += 1
        acc = [f"B{k}" for k in range(BACKGROUND // 5)]
        for _ in range(BACKGROUND):
            a, b = rng.choice(acc), rng.choice(acc)
            if a != b:
                rows.append(row(i, a, b))
                i += 1
        for k in range(0, len(rows), 5000):
            s.execute(insert(orm.Transaction), rows[k : k + 5000])
        s.commit()
        total = len(rows)
    with S() as s:
        mx = s.execute(text("select max(ingest_seq) from transactions where dataset_id=:d"), {"d": ds_id}).scalar_one()
        s.execute(text("analyze transactions"))
    snap = SimpleNamespace(dataset_id=ds_id, max_ingest_seq=mx)
    print(f"seeded rows={total} hub_peers={HUB_PEERS}")
    for depth, max_nodes in ((1, 200), (2, 200), (2, 300)):
        with S() as s:
            t = time.perf_counter()
            seen, edges, truncated = graph_view.bfs_neighborhood(s, snap, "HUB", depth, max_nodes, 1500)
            dt_ = time.perf_counter() - t
            n_q = s.execute(text("select 1")).scalar_one()
        print(
            f"  local depth={depth} max_nodes={max_nodes}: {dt_ * 1000:8.0f} ms  "
            f"nodes={len(seen)} edges={len(edges)} truncated={truncated}"
        )
    with S() as s:  # what the DB must produce for ONE expansion of the hub, before Python truncates
        t = time.perf_counter()
        n = len(
            s.execute(
                graph_view._aggregate().where(
                    *graph_view.eligible(snap),
                    (orm.Transaction.sender_account_id == "HUB") | (orm.Transaction.receiver_account_id == "HUB"),
                )
            ).all()
        )
        print(
            f"  one hub expansion returns {n} aggregate rows to Python in "
            f"{(time.perf_counter() - t) * 1000:.0f} ms (budget keeps 200 nodes / 1500 edges)"
        )
finally:
    with S() as s:
        s.execute(delete(orm.Transaction).where(orm.Transaction.dataset_id == ds_id))
        s.execute(delete(orm.ImportBatch).where(orm.ImportBatch.dataset_id == ds_id))
        s.execute(delete(orm.Dataset).where(orm.Dataset.id == ds_id))
        s.commit()
    print("cleaned up probe dataset")
