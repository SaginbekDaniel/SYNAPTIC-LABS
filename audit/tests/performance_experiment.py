"""Bounded synthetic benchmarks for the pure pipeline and a disposable API/DB."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import resource
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import psycopg

from nexora.analytics import risk
from nexora.analytics.config import default_config
from nexora.analytics.graph_builder import build_snapshot
from nexora.analytics.pipeline import run_analysis
from nexora.domain.transfers import ObservedTransfer
from nexora.ingest.csv_adapter import CsvSchemaError, read_csv_rows
from nexora.ingest.validation import prepare_batch

BASE = datetime(2026, 8, 1, tzinfo=UTC)
BASE_API = "/api/v1"
SIZES = (100, 1000, 10_000, 100_000)
HEADER = [
    "source_transaction_id",
    "sender_account_id",
    "receiver_account_id",
    "amount_minor",
    "currency",
    "occurred_at",
]
LOOPBACK = {"localhost", "127.0.0.1"}


def rows(size, *, dense=False):
    for i in range(size):
        if dense:
            group, part = divmod(i, 3)
            source, target = f"C{group}-{part}", f"C{group}-{(part + 1) % 3}"
        elif i < min(400, size):
            dest = i // 2
            source, target = ("hub", f"member{dest}") if i % 2 == 0 else (f"member{dest}", f"leaf{dest}")
        elif i % 500 in {0, 1, 2}:
            group, part = divmod(i, 500)
            source, target = f"C{group}-{part}", f"C{group}-{(part + 1) % 3}"
        else:
            pair = i // 8
            source, target = f"s{pair}", f"r{pair}"
        when = BASE + timedelta(minutes=(i // (3 if dense else 500)) % 1440 + i % (3 if dense else 500))
        yield f"tx{i}", source, target, 1_550_000 + (i % 13) * 1000, "KZT", when


def to_csv(size):
    handle = io.StringIO(newline="")
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows((*fields[:-1], fields[-1].isoformat()) for fields in rows(size))
    return handle.getvalue().encode()


def to_transfers(size, dense=False):
    return [
        ObservedTransfer(tid, tid, source, target, amount, currency, when.date(), when, "timestamp")
        for tid, source, target, amount, currency, when in rows(size, dense=dense)
    ]


def distribution(samples):
    ordered = sorted(samples)
    result = {
        "n": len(samples),
        "p50_ms": statistics.median(samples),
        "min_ms": min(ordered),
        "max_ms": max(ordered),
        "mean_ms": statistics.mean(samples),
    }
    for p in (95, 99):
        enough = len(samples) >= (20 if p == 95 else 100)
        result[f"p{p}_ms"] = ordered[math.ceil(p / 100 * len(samples)) - 1] if enough else None
    return result


def timed(function):
    start = time.perf_counter()
    result = function()
    return result, (time.perf_counter() - start) * 1000


def pure(size, dense=False):
    started_cpu = time.process_time()
    started_wall = time.perf_counter()
    content = to_csv(size)
    parse = validate = None
    ingestion_rejection = None
    if size > 200_000:
        try:
            read_csv_rows(content)
        except CsvSchemaError as exc:
            ingestion_rejection = exc.code
        else:
            raise AssertionError("The standard CSV row cap did not apply")
    else:
        (loaded, _), parse = timed(lambda: read_csv_rows(content))
        (records, report), validate = timed(
            lambda records=loaded: prepare_batch(records, source_id="audit-perf", is_synthetic=True)
        )
        assert len(records) == report.accepted == size
        del loaded, records
    transfers = to_transfers(size, dense)
    graph_times, pipeline_times = [], []
    config = default_config()
    graph = out = None
    repeats = 1 if size > 200_000 else (5 if size <= 10_000 and not dense else 2)
    for _ in range(repeats):
        graph, wall = timed(lambda: build_snapshot(transfers))
        graph_times.append(wall)
        currencies = graph.currencies
        accounts = len(graph.accounts)
        edges = sum(len(graph.by_currency[currency].edges) for currency in currencies)
        del graph
        out, wall = timed(
            lambda: run_analysis(
                dataset_id="audit-perf", transfers=transfers, contract={"declared_complete": False}, config=config
            )
        )
        pipeline_times.append(wall)
        formations, assessments, warnings = len(out.formations), len(out.assessments), out.partial_reasons
        del out
    cpu_seconds = time.process_time() - started_cpu
    wall_seconds = time.perf_counter() - started_wall
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "n": size,
        "dense": dense,
        "counts": {
            "accounts": accounts,
            "edges": edges,
            "formations": formations,
            "assessments": assessments,
            "warnings": warnings,
        },
        "csv_bytes": len(content),
        "csv_parse_ms": parse,
        "csv_rejection": ingestion_rejection,
        "csv_validate_ms": validate,
        "graph": distribution(graph_times),
        "pipeline_including_graph": distribution(pipeline_times),
        "pipeline_txs_per_second": size / (statistics.median(pipeline_times) / 1000),
        "process_cpu_seconds": cpu_seconds,
        "process_cpu_percent_of_one_core": 100 * cpu_seconds / wall_seconds,
        "process_peak_rss_mib": rss / (1024 * 1024 if sys.platform == "darwin" else 1024),
    }


def risk_timing():
    measures = []
    original = risk.assess
    for size in SIZES:
        samples = []

        def measured_assess(*args, captured=samples, **kwargs):
            result, ms = timed(lambda: original(*args, **kwargs))
            captured.append(ms)
            return result

        with patch.object(risk, "assess", measured_assess):
            out = run_analysis(
                dataset_id=f"audit-risk-{size}",
                transfers=to_transfers(size),
                contract={"declared_complete": False},
                config=default_config(),
            )
        assert len(out.assessments) == len(samples)
        measures.append(
            {"n": size, "assessments": len(samples), "total_ms": sum(samples), "per_assess": distribution(samples)}
        )
    return measures


def call_checked(client, method, path, expected=200, **kwargs):
    response, ms = timed(lambda: client.request(method, path, **kwargs))
    if response.status_code != expected:
        raise RuntimeError(f"{method} {path}: HTTP {response.status_code}, wanted {expected}")
    return response.json(), ms


def load_run(client, path, workers, params):
    hits = 120
    start = time.perf_counter()

    def hit(_):
        response, ms = timed(lambda: client.get(path, params=params))
        return response.status_code, ms

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(hit, range(hits)))
    elapsed = time.perf_counter() - start
    ok = [ms for status, ms in results if status == 200]
    return {
        "concurrency": workers,
        "route": path,
        "n": hits,
        "wall_seconds": elapsed,
        "throughput_rps": hits / elapsed,
        "error_rate": 1 - len(ok) / hits,
        "latency": distribution(ok) if ok else None,
    }


def api_benchmark(url, dsn):
    api = urlparse(url)
    db = urlparse(dsn)
    assert api.hostname in LOOPBACK and db.hostname in LOOPBACK and db.path.endswith("_audit_perf")
    report = []
    with httpx.Client(base_url=url, timeout=120, trust_env=False, limits=httpx.Limits(max_connections=32)) as client:
        for size in SIZES:
            content = to_csv(size)
            imported, ingest = call_checked(
                client,
                "POST",
                f"{BASE_API}/datasets/import",
                201,
                data={"name": f"audit-perf-{size}"},
                files={"file": ("synthetic.csv", content, "text/csv")},
            )
            assert imported["report"]["accepted"] == size
            dataset = imported["dataset"]["id"]
            job, submit = call_checked(client, "POST", f"{BASE_API}/analysis/jobs", 202, json={"dataset_id": dataset})
            start = time.perf_counter()
            while time.perf_counter() - start < 100:
                job, _ = call_checked(client, "GET", f"{BASE_API}/analysis/jobs/{job['id']}")
                if job["status"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(0.1)
            if job["status"] != "succeeded":
                raise RuntimeError(f"Worker did not complete synthetic job {size}: {job['status']}")
            wait = (time.perf_counter() - start) * 1000
            snap = job["snapshot_id"]
            paths = {
                "transactions": (f"{BASE_API}/snapshots/{snap}/transactions", {"limit": 50}),
                "neighborhood_depth_1": (
                    f"{BASE_API}/snapshots/{snap}/neighborhood",
                    {"account_id": "hub", "depth": 1},
                ),
                "neighborhood_depth_2": (
                    f"{BASE_API}/snapshots/{snap}/neighborhood",
                    {"account_id": "hub", "depth": 2},
                ),
                "alerts": (f"{BASE_API}/alerts", {"dataset_id": dataset, "limit": 50}),
                "overview": (f"{BASE_API}/datasets/{dataset}/overview", {}),
            }
            latencies = {}
            for name, (path, params) in paths.items():
                call_checked(client, "GET", path, params=params)
                latencies[name] = distribution([call_checked(client, "GET", path, params=params)[1] for _ in range(25)])
            with psycopg.connect(dsn) as conn:
                query = conn.execute(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT count(*) FROM transactions WHERE dataset_id=%s",
                    (dataset,),
                ).fetchone()[0][0]
            entry = {
                "n": size,
                "import_ms": ingest,
                "csv_bytes": len(content),
                "job_enqueue_ms": submit,
                "queue_to_observed_completion_ms": wait,
                "db_count_execution_ms": query["Execution Time"],
                "db_count_plan": query["Plan"],
                "api_latency": latencies,
            }
            if size == SIZES[-1]:
                path, params = paths["transactions"]
                entry["concurrency"] = [load_run(client, path, count, params) for count in (1, 4, 12, 24)]
            report.append(entry)
            print(f"{size} rows import {ingest:.2f}ms, worker {wait:.2f}ms", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, choices=(*SIZES, 1_000_000))
    parser.add_argument("--dense", action="store_true")
    parser.add_argument("--risk-timing", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--dsn")
    args = parser.parse_args()
    if args.risk_timing:
        result = risk_timing()
    elif args.size:
        result = pure(args.size, args.dense)
    else:
        result = api_benchmark(args.url, args.dsn)
    args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
