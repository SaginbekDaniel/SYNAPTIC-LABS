"""Functional and data-integrity audit checks using synthetic transactions only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fraud_experiment import CONTRACT, SCENARIOS, materialize
from sqlalchemy.engine import make_url

from nexora.analytics.config import default_config
from nexora.analytics.pipeline import run_analysis
from nexora.api.main import create_app
from nexora.ingest.csv_adapter import CsvSchemaError, read_csv_rows
from nexora.ingest.validation import prepare_batch
from nexora.persistence.db import session_factory
from nexora.settings import Settings
from nexora.worker.runner import drain

BASE = "/api/v1"
CID = "not-a-uuid"
DB_ENV = "NEXORA_AUDIT_DATABASE_URL"
CSV_HEADER = "source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,occurred_at\n"
CSV_DATA = CSV_HEADER + (
    "a,s1,s2,4750000,KZT,2026-06-01T00:00:00Z\n"
    "b,s2,s3,4710000,KZT,2026-06-01T00:15:00Z\n"
    "c,s3,s1,4590000,KZT,2026-06-01T00:30:00Z\n"
)


@pytest.fixture(scope="module")
def audit_settings():
    raw = os.environ.get(DB_ENV)
    if not raw:
        pytest.skip(f"Set {DB_ENV} to the disposable test database.")
    url = make_url(raw)
    assert url.host in {"localhost", "127.0.0.1"} and (url.database or "").endswith("_audit_test")
    return Settings(database_url=raw, _env_file=None)


@pytest.fixture()
def client(audit_settings):
    with TestClient(create_app(audit_settings), raise_server_exceptions=False) as api:
        yield api


CSV_BYTES = CSV_DATA.encode()


def import_csv(client, content=CSV_BYTES, *, name=None):
    return client.post(
        f"{BASE}/datasets/import",
        data={"name": name or f"audit-{uuid4()}"},
        files={"file": ("audit.csv", content, "text/csv")},
    )


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["request_id"] == response.headers["x-request-id"]
    assert error["message"] and isinstance(error["details"], dict)


@pytest.mark.parametrize(
    "path",
    [
        f"/datasets/{CID}",
        f"/datasets/{CID}/overview",
        f"/analysis/jobs/{CID}",
        f"/analysis/snapshots/{CID}",
        f"/snapshots/{CID}/neighborhood?account_id=a",
        f"/snapshots/{CID}/activity",
        f"/snapshots/{CID}/accounts/a",
        f"/snapshots/{CID}/transactions",
        f"/transactions/{CID}",
        f"/alerts/{CID}",
        f"/alerts/{CID}/evidence",
        f"/cases/{CID}",
        f"/cases/{CID}/audit",
    ],
)
def test_invalid_identifiers_return_the_documented_envelope(client, path):
    assert_error(client.get(BASE + path), 422, "INVALID_ID")


@pytest.mark.parametrize(
    "path,body",
    [
        ("/analysis/jobs", {}),
        ("/cases", {}),
        (f"/cases/{CID}/decisions", {}),
        (f"/cases/{CID}/notes", {"body": ""}),
        ("/lab/datasets", {"suite": []}),
        ("/demo/transfer-checks", {"amount_minor": 10}),
        ("/datasets/import", {}),
    ],
)
def test_missing_or_wrong_types_are_rejected(client, path, body):
    assert_error(client.post(BASE + path, json=body), 422, "REQUEST_INVALID")


def test_http_method_error_keeps_allow_header():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.patch("/health/live")
    assert_error(response, 405, "METHOD_NOT_ALLOWED")
    assert "GET" in response.headers.get("allow", "").split(", ")


def test_validation_does_not_poison_the_following_request(client):
    assert_error(import_csv(client, b"unknown\nvalue\n"), 422, "CSV_SCHEMA_INVALID")
    result = import_csv(client)
    assert result.status_code == 201
    assert result.json()["report"]["accepted"] == 3
    assert client.get(f"{BASE}/datasets/{result.json()['dataset']['id']}").status_code == 200


def test_same_csv_submission_is_idempotent(client):
    name = f"audit-{uuid4()}"
    first, second = [import_csv(client, name=name) for _ in range(2)]
    assert first.status_code == second.status_code == 201
    assert first.json()["dataset"]["id"] == second.json()["dataset"]["id"]


def test_out_of_range_csv_records_are_quarantined():
    rows, _ = read_csv_rows((CSV_DATA + "d,s1,s3,1e4,KZT,2026-06-01T01:00:00Z\n").encode())
    clean, report = prepare_batch(rows, source_id="audit", is_synthetic=True)
    assert len(clean) == 3 and report.quarantined == 1


def test_empty_csv_cannot_be_analyzed(client):
    imported = import_csv(client, CSV_HEADER.encode())
    assert imported.status_code == 201 and imported.json()["report"]["accepted"] == 0
    assert_error(
        client.post(f"{BASE}/analysis/jobs", json={"dataset_id": imported.json()["dataset"]["id"]}),
        422,
        "DATASET_EMPTY",
    )


def test_upload_limit_controls_small_isolated_fixture(audit_settings):
    small = audit_settings.model_copy(update={"max_upload_bytes": 64})
    with TestClient(create_app(small)) as client:
        assert_error(import_csv(client), 413, "UPLOAD_TOO_LARGE")


def test_csv_rejects_duplicate_headers():
    ambiguous = CSV_HEADER.replace("amount_minor", "amount_minor,amount_minor") + (
        "a,s1,s2,4750000,1,KZT,2026-06-01T00:00:00Z\n"
    )
    with pytest.raises(CsvSchemaError, match="column"):
        read_csv_rows(ambiguous.encode())


def test_distinct_file_records_keep_exact_money_and_order_invariance():
    rows = CSV_DATA.splitlines()
    a, _ = read_csv_rows(CSV_DATA.encode())
    b, _ = read_csv_rows(("\n".join([rows[0], *reversed(rows[1:])]) + "\n").encode())
    records = [prepare_batch(values, source_id="audit", is_synthetic=True)[0] for values in (a, b)]
    signatures = [sorted((item.source_transaction_id, item.amount_minor) for item in record) for record in records]
    assert signatures[0] == signatures[1] == [("a", 4750000), ("b", 4710000), ("c", 4590000)]


def test_concurrent_duplicate_analysis_and_csv_to_case(client, audit_settings):
    imported = import_csv(client)
    assert imported.status_code == 201
    dataset_id = imported.json()["dataset"]["id"]
    payload = {"dataset_id": dataset_id, "idempotency_key": f"audit-{uuid4()}"}

    def submit(_):
        return client.post(f"{BASE}/analysis/jobs", json=payload)

    with ThreadPoolExecutor(max_workers=6) as workers:
        responses = list(workers.map(submit, range(6)))
    assert {response.status_code for response in responses} == {202}
    assert len({response.json()["id"] for response in responses}) == 1
    assert len({response.headers["Location"] for response in responses}) == 1
    location = responses[0].headers["Location"]
    drain(session_factory(audit_settings.database_url), config=default_config())
    job = client.get(location).json()
    assert job["status"] == "succeeded"
    snapshot_path = f"{BASE}/snapshots/{job['snapshot_id']}"
    assert client.get(f"{BASE}/analysis/snapshots/{job['snapshot_id']}").status_code == 200
    transfers = client.get(f"{snapshot_path}/transactions").json()["items"]
    assert {tx["source_transaction_id"] for tx in transfers} == {"a", "b", "c"}
    assert client.get(f"{BASE}/transactions/{transfers[0]['id']}").json() == transfers[0]
    assert client.get(f"{snapshot_path}/neighborhood", params={"account_id": "s1", "depth": 2}).json()["found"]
    queue = client.get(f"{BASE}/alerts", params={"dataset_id": dataset_id}).json()
    alert = next(item for item in queue["items"] if item["formation"]["kind"] == "cycle")
    evidence = client.get(f"{BASE}/alerts/{alert['id']}/evidence").json()
    assert {tx["id"] for tx in evidence["transactions"]} == {tx["id"] for tx in transfers}
    created = client.post(f"{BASE}/cases", json={"alert_id": alert["id"]})
    assert created.status_code == 201
    case = f"{BASE}/cases/{created.json()['id']}"
    assert (
        client.post(f"{case}/decisions", json={"to_status": "investigating", "expected_version": 1}).status_code == 200
    )
    assert (
        client.post(
            f"{case}/decisions",
            json={"to_status": "escalated", "expected_version": 2, "reason": "Synthetic audit escalation"},
        ).status_code
        == 200
    )
    assert client.get(case).json()["status"] == "escalated"
    assert [event["action"] for event in client.get(f"{case}/audit").json()] == [
        "case.opened",
        "case.investigating",
        "case.escalated",
    ]


def test_independent_evidence_references_resolve_and_output_is_deterministic():
    for index, scenario in enumerate(SCENARIOS):
        transactions = list(materialize(scenario, f"s{index:02}"))
        kwargs = {"dataset_id": scenario.name, "contract": CONTRACT, "config": default_config()}
        first = run_analysis(transfers=transactions, **kwargs)
        second = run_analysis(transfers=list(reversed(transactions)), **kwargs)
        for key in ("snapshot_id", "formations", "signals", "assessments", "evidence", "partial_reasons"):
            assert getattr(first, key) == getattr(second, key)
        assert not first.quarantined
        ids = {tx.transaction_id for tx in transactions}
        accounts = {actor for tx in transactions for actor in (tx.sender, tx.receiver)}
        assert all(set(item.transaction_ids) <= ids and set(item.account_ids) <= accounts for item in first.evidence)


def test_missing_benchmark_artifact_reports_not_found(tmp_path: Path):
    settings = Settings(benchmark_artifact=str(tmp_path / "missing.json"), _env_file=None)
    with TestClient(create_app(settings)) as client:
        response = client.get(f"{BASE}/evaluation")
    assert_error(response, 404, "BENCHMARK_NOT_FOUND")
