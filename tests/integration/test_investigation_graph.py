"""Investigation graph read model (graph-view-v1) against a real PostgreSQL snapshot."""

import pytest

from tests.integration.test_api import _create_and_analyse

pytestmark = pytest.mark.integration

BAND_RANK = {"critical": 0, "high": 1, "medium": 2, "insufficient_evidence": 3, "low": 4}


def _graph(client, snapshot_id, **params):
    r = client.get(f"/api/v1/snapshots/{snapshot_id}/graph", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _edge_tx(client, snapshot_id, e):
    r = client.get(
        f"/api/v1/snapshots/{snapshot_id}/edge-transactions",
        params={"sender": e["sender"], "receiver": e["receiver"], "currency": e["currency"], "limit": 500},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_overview_carries_snapshot_identity_and_only_stored_risk(client, settings):
    ds_id, job = _create_and_analyse(client, settings, seed=4101)
    sid = job["snapshot_id"]
    snap = client.get(f"/api/v1/analysis/snapshots/{sid}").json()
    g = _graph(client, sid)

    assert g["mode"] == "overview" and g["found"] and g["view_version"] == "graph-view-v1"
    assert (g["snapshot_id"], g["dataset_id"]) == (sid, ds_id)
    assert g["config_sha256"] == snap["config_sha256"] and g["policy_version"] == snap["policy_version"]

    # Formations arrive in the Review Queue's server ranking, and each band/priority is the stored one.
    ranks = [(BAND_RANK[f["band"]], -(f["priority"] or 0)) for f in g["formations"]]
    assert ranks == sorted(ranks)
    by_formation = {f["id"]: f for f in g["formations"]}
    for f in g["formations"]:
        if f["alert_id"]:
            alert = client.get(f"/api/v1/alerts/{f['alert_id']}").json()
            assert (alert["risk"]["band"], alert["risk"]["priority"]) == (f["band"], f["priority"])

    # A node's band is the strongest band among its own formations — never derived from the drawing.
    for n in g["nodes"]:
        refs = [by_formation[r["formation_id"]] for r in n["formations"]]
        assert refs, "overview nodes all belong to a formation"
        best = min(refs, key=lambda f: (BAND_RANK[f["band"]], -(f["priority"] or 0)))
        assert (n["band"], n["priority"]) == (best["band"], best["priority"])
        assert n["hop"] is None


def test_every_edge_recomputes_from_its_source_transactions(client, settings):
    _, job = _create_and_analyse(client, settings, seed=4102)
    sid = job["snapshot_id"]
    g = _graph(client, sid, max_nodes=60)
    assert g["edges"]
    for e in g["edges"]:
        assert e["kind"] == "observed_transfer"
        assert isinstance(e["amount_minor"], str) and e["amount_minor"].isdigit()
        page = _edge_tx(client, sid, e)
        assert page["total"] == e["n_transactions"]
        assert sum(int(t["amount_minor"]) for t in page["items"]) == int(e["amount_minor"])
        assert all(
            (t["sender_account_id"], t["receiver_account_id"], t["currency"], t["status"])
            == (e["sender"], e["receiver"], e["currency"], "posted")
            for t in page["items"]
        )


def test_evidence_edges_are_exactly_the_pairs_cited_by_formation_evidence(client, settings):
    _, job = _create_and_analyse(client, settings, seed=4103)
    sid = job["snapshot_id"]
    g = _graph(client, sid, max_formations=8)
    formations = {f["id"]: f for f in g["formations"]}
    cited: dict[str, set[tuple[str, str, str]]] = {}
    for f in formations.values():
        if not f["alert_id"]:
            continue
        chain = client.get(f"/api/v1/alerts/{f['alert_id']}/evidence").json()
        cited[f["id"]] = {
            (t["sender_account_id"], t["receiver_account_id"], t["currency"])
            for t in chain["transactions"]
            if t["status"] == "posted" and t["sender_account_id"] != t["receiver_account_id"]
        }
    edges = {(e["sender"], e["receiver"], e["currency"]): e for e in g["edges"]}
    assert cited and any(e["evidence_formation_ids"] for e in edges.values()), "fixture must exercise evidence"
    for fid, pairs in cited.items():
        for pair in pairs:
            if pair in edges:
                assert fid in edges[pair]["evidence_formation_ids"]
    for pair, e in edges.items():
        for fid in e["evidence_formation_ids"]:
            assert fid in formations
            if fid in cited:
                assert pair in cited[fid]
        # The edge has no temporal status of its own: only those of the formations it evidences.
        expected = sorted({formations[fid]["temporal_status"] or "unavailable" for fid in e["evidence_formation_ids"]})
        assert e["temporal_statuses"] == expected


def test_overview_budget_keeps_whole_formations_and_reports_truncation(client, settings):
    _, job = _create_and_analyse(client, settings, seed=4104)
    sid = job["snapshot_id"]
    full = _graph(client, sid, max_formations=10**6, max_nodes=10**6)
    assert full["limits"]["max_nodes"] == settings.graph_max_nodes
    assert full["limits"]["max_formations"] == settings.graph_max_formations

    assert full["limits"]["formations_total"] >= len(full["formations"])
    if "max_formations" not in full["limits"]["reasons"] and "max_nodes" not in full["limits"]["reasons"]:
        assert full["limits"]["formations_total"] == len(full["formations"])
    few = _graph(client, sid, max_formations=2)
    assert len(few["formations"]) <= 2 and few["limits"]["formations_total"] == full["limits"]["formations_total"]
    assert "max_formations" in few["limits"]["reasons"] or full["limits"]["formations_total"] <= 2

    small = _graph(client, sid, max_nodes=8)
    assert len(small["nodes"]) <= 8
    assert small["limits"]["truncated"] and small["limits"]["reasons"]
    assert small["formations"]
    node_ids = {n["account_id"] for n in small["nodes"]}
    for f in small["formations"]:
        members = {
            n["account_id"] for n in small["nodes"] if any(r["formation_id"] == f["id"] for r in n["formations"])
        }
        assert len(members) == f["account_count"], "a formation is drawn whole or not at all"
    assert all(e["sender"] in node_ids and e["receiver"] in node_ids for e in small["edges"])


def test_filters_select_formations_by_stored_band_and_kind(client, settings):
    _, job = _create_and_analyse(client, settings, seed=4105)
    sid = job["snapshot_id"]
    g = _graph(client, sid, band=["medium"], kind=["funnel", "fan_out"])
    assert g["formations"], "fixture must contain medium funnels/fan-outs"
    assert all(f["band"] == "medium" and f["kind"] in ("funnel", "fan_out") for f in g["formations"])
    r = client.get(f"/api/v1/snapshots/{sid}/graph", params={"band": "certain"})
    assert r.status_code == 422


def test_local_mode_round_trips_big_ids_and_filters_eligibility(client, settings):
    big = "9007199254740993"  # 2^53 + 1: must never become a float anywhere
    csv = (
        "source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,observed_date,status\n"
        f"t1,{big},B,90071992547409930,KZT,2026-07-01,posted\n"
        f"t2,{big},B,5,KZT,2026-07-02,reversed\n"
        f"t3,B,{big},7,KZT,2026-07-03,posted\n"
        "t4,B,C,100,KZT,2026-07-04,posted\n"
    )
    r = client.post("/api/v1/datasets/import", files={"file": ("x.csv", csv.encode())}, data={"name": "graph ids"})
    assert r.status_code == 201, r.text
    ds_id = r.json()["dataset"]["id"]
    from nexora.analytics.config import default_config
    from nexora.persistence.db import session_factory
    from nexora.worker.runner import drain

    client.post("/api/v1/analysis/jobs", json={"dataset_id": ds_id})
    drain(session_factory(settings.database_url), config=default_config())
    sid = client.get(f"/api/v1/datasets/{ds_id}").json()["latest_snapshot"]["id"]

    g = _graph(client, sid, mode="local", account_id=big, depth=2)
    assert g["found"] and g["center"] == big
    assert {n["account_id"]: n["hop"] for n in g["nodes"]} == {big: 0, "B": 1, "C": 2}
    out = next(e for e in g["edges"] if e["sender"] == big)
    assert out["amount_minor"] == "90071992547409930" and out["n_transactions"] == 1  # reversed row excluded
    page = _edge_tx(client, sid, out)
    assert [t["source_transaction_id"] for t in page["items"]] == ["t1"]  # not t2 (reversed), not t3 (reverse)

    missing = _graph(client, sid, mode="local", account_id="nobody")
    assert missing["found"] is False and missing["edges"] == []


def test_graph_rejects_bad_requests_without_leaking(client, anon_client, settings):
    _, job = _create_and_analyse(client, settings, seed=4106)
    sid = job["snapshot_id"]
    assert client.get(f"/api/v1/snapshots/{sid}/graph", params={"mode": "local"}).json()["error"]["code"] == (
        "ACCOUNT_REQUIRED"
    )
    assert client.get(f"/api/v1/snapshots/{sid}/graph", params={"mode": "global"}).status_code == 422
    assert client.get(f"/api/v1/snapshots/{sid}/graph", params={"depth": 3}).status_code == 422
    unknown = client.get("/api/v1/snapshots/00000000-0000-0000-0000-000000000000/graph")
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"
    bad = client.get(
        f"/api/v1/snapshots/{sid}/edge-transactions", params={"sender": "A", "receiver": "A", "currency": "KZT"}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "SELF_EDGE"
    assert anon_client.get(f"/api/v1/snapshots/{sid}/graph").status_code == 401
    assert (
        anon_client.get(
            f"/api/v1/snapshots/{sid}/edge-transactions", params={"sender": "A", "receiver": "B", "currency": "KZT"}
        ).status_code
        == 401
    )
