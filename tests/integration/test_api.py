import pytest

from nexora.analytics.config import default_config
from nexora.persistence.db import session_factory
from nexora.worker.runner import drain

pytestmark = pytest.mark.integration


def _create_and_analyse(client, settings, seed=2026, suite="demo-v1"):
    r = client.post("/api/v1/lab/datasets", json={"suite": suite, "seed": seed})
    assert r.status_code == 201, r.text
    body = r.json()
    ds_id = body["dataset"]["id"]
    assert body["report"]["accepted"] == body["report"]["processed"]
    r = client.post("/api/v1/analysis/jobs", json={"dataset_id": ds_id})
    assert r.status_code == 202
    job_id = r.json()["id"]
    drain(session_factory(settings.database_url), config=default_config())
    job = client.get(f"/api/v1/analysis/jobs/{job_id}").json()
    assert job["status"] == "succeeded"
    return ds_id, job


def test_end_to_end_transaction_to_audited_decision(client, settings):  # UI-001 backend path
    ds_id, job = _create_and_analyse(client, settings)
    alerts = client.get("/api/v1/alerts", params={"dataset_id": ds_id}).json()
    assert alerts["total"] > 0
    bands = [a["risk"]["band"] for a in alerts["items"]]
    assert "high" in bands and "insufficient_evidence" in bands and "low" not in bands
    top = alerts["items"][0]
    assert top["risk"]["band"] == "high" and top["in_latest_snapshot"]

    detail = client.get(f"/api/v1/alerts/{top['id']}").json()
    assert {e["kind"] for e in detail["evidence"]} >= {"graph_fact", "coverage_fact"}
    assert detail["snapshot"]["id"] == job["snapshot_id"]
    chain = client.get(f"/api/v1/alerts/{top['id']}/evidence").json()
    tx_by_id = {t["id"]: t for t in chain["transactions"]}
    structural = next(e for e in chain["evidence"] if e["kind"] == "graph_fact")
    assert all(t in tx_by_id for t in structural["transaction_ids"])
    # Recompute the claimed total from the source transfers returned by the API.
    assert sum(int(tx_by_id[t]["amount_minor"]) for t in structural["transaction_ids"]) == int(
        structural["observations"]["total_minor"]
    )
    assert all(isinstance(t["amount_minor"], str) for t in chain["transactions"])
    assert all(t["occurred_at"] is None and t["time_precision"] == "day" for t in chain["transactions"])

    r = client.post("/api/v1/cases", json={"alert_id": top["id"]})
    assert r.status_code == 201
    case = r.json()
    assert client.post("/api/v1/cases", json={"alert_id": top["id"]}).status_code == 200  # idempotent
    r = client.post(f"/api/v1/cases/{case['id']}/decisions", json={"to_status": "investigating", "expected_version": 1})
    assert r.status_code == 200 and r.json()["version"] == 2
    r = client.post(
        f"/api/v1/cases/{case['id']}/decisions",
        json={"to_status": "escalated", "expected_version": 1, "reason": "x"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "CASE_VERSION_CONFLICT"
    r = client.post(
        f"/api/v1/cases/{case['id']}/decisions",
        json={"to_status": "escalated", "expected_version": 2, "reason": "Цепочка подтверждена"},
    )
    assert r.status_code == 200 and r.json()["status"] == "escalated"
    note = '<img src=x onerror="alert(1)">'
    r = client.post(f"/api/v1/cases/{case['id']}/notes", json={"body": note})
    assert r.status_code == 201 and r.json()["notes"][0]["body"] == note  # stored verbatim, rendered as text by the UI
    audit = client.get(f"/api/v1/cases/{case['id']}/audit").json()
    assert [a["action"] for a in audit] == [
        "case.opened",
        "case.investigating",
        "case.escalated",
        "case.note_added",
    ]
    assert audit[2]["reason"] == "Цепочка подтверждена" and audit[2]["request_id"]
    assert client.get("/api/v1/alerts", params={"dataset_id": ds_id, "status": "in_case"}).json()["total"] == 1


def test_big_account_ids_round_trip_exactly(client, settings):  # DATA-001
    big = "9007199254740993"  # 2^53 + 1
    csv = (
        "source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,observed_date\n"
        f"t1,{big},B,90071992547409930,KZT,2026-07-01\n"
        "t2,B,C,100,KZT,2026-07-02\n"
        "t3,B,C,100,KZT,not-a-date\n"
    )
    r = client.post("/api/v1/datasets/import", files={"file": ("x.csv", csv.encode())}, data={"name": "big ids"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["report"]["accepted"] == 2 and body["report"]["error_codes"] == {"DATE_INVALID": 1}
    ds_id = body["dataset"]["id"]
    client.post("/api/v1/analysis/jobs", json={"dataset_id": ds_id})
    drain(session_factory(settings.database_url), config=default_config())
    snap = client.get(f"/api/v1/datasets/{ds_id}").json()["latest_snapshot"]
    acc = client.get(f"/api/v1/snapshots/{snap['id']}/accounts/{big}").json()
    assert acc["found"] and acc["account_id"] == big and acc["outgoing_minor"] == "90071992547409930"
    hood = client.get(f"/api/v1/snapshots/{snap['id']}/neighborhood", params={"account_id": big, "depth": 2}).json()
    assert hood["edges"][0]["sender"] == big
    missing = client.get(f"/api/v1/snapshots/{snap['id']}/accounts/does-not-exist").json()
    assert missing["found"] is False and missing["formations"] == []  # UI-002 honest no-result


def test_graph_limits_are_clamped(client, settings):  # SEC-002
    ds_id, job = _create_and_analyse(client, settings, seed=77)
    alert = client.get("/api/v1/alerts", params={"dataset_id": ds_id}).json()["items"][0]
    account = alert["formation"]["subject_account_id"]
    r = client.get(
        f"/api/v1/snapshots/{job['snapshot_id']}/neighborhood",
        params={"account_id": account, "depth": 50, "max_nodes": 10**6},
    )
    body = r.json()
    assert r.status_code == 200 and body["depth"] == settings.graph_max_depth
    assert body["limits"]["max_nodes"] == settings.graph_max_nodes and len(body["nodes"]) <= settings.graph_max_nodes


def test_error_envelope(client):
    r = client.get("/api/v1/alerts/not-a-uuid")
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_ID" and r.json()["error"]["request_id"]
    r = client.get("/api/v1/alerts/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["error"]["code"] == "ALERT_NOT_FOUND"
    r = client.post("/api/v1/lab/datasets", json={"suite": "demo-v1", "seed": -1})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REQUEST_INVALID"
    r = client.post("/api/v1/lab/datasets", json={"suite": "nope", "seed": 1})
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNKNOWN_SUITE"
    assert client.get("/health/ready").json()["status"] == "ok"
