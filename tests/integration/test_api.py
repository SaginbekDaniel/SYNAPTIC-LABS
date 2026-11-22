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
    settings.allow_csv_import = True  # the import route is off by default (B-010)
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


def test_activity_counts_match_source_transfers(client, settings):
    ds_id, job = _create_and_analyse(client, settings, seed=4242)
    snap_id = job["snapshot_id"]
    snap = client.get(f"/api/v1/analysis/snapshots/{snap_id}").json()
    act = client.get(f"/api/v1/snapshots/{snap_id}/activity")
    assert act.status_code == 200, act.text
    days = act.json()["days"]
    # Contiguous calendar days spanning exactly the snapshot window, zero-filled.
    assert days[0]["date"] == snap["window_start"] and days[-1]["date"] == snap["window_end"]
    assert len({d["date"] for d in days}) == len(days)
    assert sum(d["transactions"] for d in days) == snap["transactions_count"]
    # Evidence transfers of alerted formations, recomputed from the per-alert evidence chains.
    cited: dict[str, str] = {}
    alerts = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "limit": 200}).json()["items"]
    for a in alerts:
        for t in client.get(f"/api/v1/alerts/{a['id']}/evidence").json()["transactions"]:
            cited[t["id"]] = t["observed_date"]
    by_day: dict[str, int] = {}
    for date in cited.values():
        by_day[date] = by_day.get(date, 0) + 1
    assert {d["date"]: d["in_alerts"] for d in days if d["in_alerts"]} == by_day
    assert all(0 <= d["in_alerts"] <= d["transactions"] for d in days)
    assert client.get("/api/v1/snapshots/not-a-uuid/activity").status_code == 422


def test_alert_list_pages_searches_sorts_and_counts_on_the_server(client, settings):
    """The queue must not depend on loading every alert: totals, facets, search and sort are server-side."""
    ds_id, _ = _create_and_analyse(client, settings)
    everything = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "limit": 200}).json()
    items = everything["items"]
    total = everything["total"]
    assert total == len(items) > 2

    # Facets cover the whole filtered set and agree with the items.
    bands: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for a in items:
        bands[a["risk"]["band"]] = bands.get(a["risk"]["band"], 0) + 1
        kinds[a["formation"]["kind"]] = kinds.get(a["formation"]["kind"], 0) + 1
    assert everything["band_counts"] == bands and everything["kind_counts"] == kinds

    # Paging: limit 1 still reports the full total and full facets; pages concatenate to the full order.
    pages = [
        client.get("/api/v1/alerts", params={"dataset_id": ds_id, "limit": 2, "offset": o}).json()
        for o in range(0, total, 2)
    ]
    assert all(p["total"] == total and p["band_counts"] == bands for p in pages)
    assert [a["id"] for p in pages for a in p["items"]] == [a["id"] for a in items]

    # Band filter narrows items but band facet stays unfiltered by band.
    some_band = items[0]["risk"]["band"]
    by_band = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "band": some_band, "limit": 200}).json()
    assert by_band["total"] == bands[some_band] and by_band["band_counts"] == bands
    assert {a["risk"]["band"] for a in by_band["items"]} == {some_band}

    # Search matches any member account (case-insensitive) and escapes LIKE wildcards.
    member = items[-1]["formation"]["subject_account_id"]
    hits = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "q": member.lower(), "limit": 200}).json()
    assert items[-1]["id"] in {a["id"] for a in hits["items"]}
    assert sum(hits["band_counts"].values()) == hits["total"]
    assert client.get("/api/v1/alerts", params={"dataset_id": ds_id, "q": "%"}).json()["total"] == 0
    assert client.get("/api/v1/alerts", params={"dataset_id": ds_id, "q": "_"}).json()["total"] == 0

    # Sorts are applied before paging.
    for sort, key in (
        ("accounts", lambda a: a["formation"]["member_count"]),
        ("transfers", lambda a: a["transaction_count"]),
        ("recent", lambda a: a["formation"]["window_end"]),
    ):
        got = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "sort": sort, "limit": 200}).json()["items"]
        values = [key(a) for a in got]
        assert values == sorted(values, reverse=True), sort
        first = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "sort": sort, "limit": 1}).json()
        assert first["items"][0]["id"] == got[0]["id"]
    assert client.get("/api/v1/alerts", params={"sort": "bogus"}).status_code == 422


# -- CSV import gate (H-02, backlog B-010) --------------------------------------------------------
_IMPORT_CSV = (
    "source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,observed_date\n"
    "g1,A,B,100,KZT,2026-07-01\n"
)


def _row_counts(settings) -> dict[str, int]:
    from sqlalchemy import create_engine, text

    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as c:
            return {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in _IMPORTED_TABLES}
    finally:
        engine.dispose()


_IMPORTED_TABLES = ("datasets", "import_batches", "transactions")


def test_csv_import_is_refused_by_default_and_stores_nothing(client, settings):
    from nexora.settings import Settings

    assert Settings.model_fields["allow_csv_import"].default is False
    assert settings.allow_csv_import is False
    before = _row_counts(settings)
    r = client.post("/api/v1/datasets/import", files={"file": ("x.csv", _IMPORT_CSV.encode())}, data={"name": "real?"})
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "CSV_IMPORT_DISABLED" and r.json()["error"]["request_id"]
    assert _row_counts(settings) == before
    # The synthetic lab path is unaffected.
    assert client.post("/api/v1/lab/datasets", json={"suite": "demo-v1", "seed": 4242}).status_code == 201


def test_disabled_csv_import_is_still_authenticated_first(anon_client, client, settings):
    files, data = {"file": ("x.csv", _IMPORT_CSV.encode())}, {"name": "x"}
    r = anon_client.post("/api/v1/datasets/import", files=files, data=data)
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTH_REQUIRED"  # nothing learnt about the flag
    csrf = client.headers.pop("X-CSRF-Token")
    try:
        r = client.post("/api/v1/datasets/import", files=files, data=data)
        assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    finally:
        client.headers["X-CSRF-Token"] = csrf


def _asgi_import(app, client) -> tuple[int, list[str]]:
    """POST a multipart upload straight into the ASGI app and record when the body is pulled."""
    import anyio

    events: list[str] = []
    body = (
        b'--x\r\nContent-Disposition: form-data; name="name"\r\n\r\nasgi\r\n'
        b'--x\r\nContent-Disposition: form-data; name="file"; filename="x.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n" + _IMPORT_CSV.encode() + b"\r\n--x--\r\n"
    )
    cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/v1/datasets/import",
        "raw_path": b"/api/v1/datasets/import",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"cookie", cookie.encode()),
            (b"x-csrf-token", client.headers["X-CSRF-Token"].encode()),
            (b"content-type", b"multipart/form-data; boundary=x"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 443),
    }
    status: list[int] = []
    sent_body = False

    async def receive() -> dict:
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            events.append("body-read")
            return {"type": "http.request", "body": body, "more_body": False}
        await anyio.sleep_forever()  # a client that never disconnects
        raise AssertionError("unreachable")

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            status.append(message["status"])
            events.append("response")

    async def run() -> None:
        with anyio.move_on_after(10):
            await app(scope, receive, send)

    anyio.run(run)
    return status[0], events


def test_disabled_csv_import_refuses_before_reading_the_upload(client, settings):
    from nexora.api.main import create_app

    status, events = _asgi_import(create_app(settings), client)
    assert status == 403
    assert "body-read" not in events[: events.index("response")], events

    # Control: with the import enabled the same request is read (and accepted), so the probe detects reads.
    settings.allow_csv_import = True
    try:
        status, events = _asgi_import(create_app(settings), client)
    finally:
        settings.allow_csv_import = False
    assert status == 201
    assert events.index("body-read") < events.index("response"), events
