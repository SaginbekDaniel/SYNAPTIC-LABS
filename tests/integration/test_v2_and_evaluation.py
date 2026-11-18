"""detectors-v2 through PostgreSQL, and the evaluation read model."""

from __future__ import annotations

import json

import pytest

from tests.integration.test_api import _create_and_analyse

pytestmark = pytest.mark.integration


def test_v2_formations_publish_and_render_through_the_api(client, settings):
    # bench-v1 seed 1001 contains a coordinated distribution and a circular flow (see generator).
    ds_id, job = _create_and_analyse(client, settings, seed=1001, suite="bench-v1")
    alerts = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "limit": 200}).json()["items"]
    kinds = {a["formation"]["kind"] for a in alerts}
    assert {"fan_out", "cycle"} <= kinds, kinds
    for kind in ("fan_out", "cycle"):
        filtered = client.get("/api/v1/alerts", params={"dataset_id": ds_id, "kind": kind}).json()
        assert filtered["total"] >= 1 and all(a["formation"]["kind"] == kind for a in filtered["items"])
    fan = next(a for a in alerts if a["formation"]["kind"] == "fan_out")
    detail = client.get(f"/api/v1/alerts/{fan['id']}").json()
    families = {s["family"] for s in detail["signals"]}
    assert {"STRUCTURE", "TEMPORAL", "PEER_STATISTICS"} <= families
    assert detail["risk"]["policy_version"] == "risk-policy-v2"
    chain = client.get(f"/api/v1/alerts/{fan['id']}/evidence").json()
    peer = [e for e in chain["evidence"] if "window_minor" in e["observations"]]
    assert peer, "peer evidence must be published with its window transactions"
    by_id = {t["id"]: t for t in chain["transactions"]}
    window = peer[0]
    assert sum(int(by_id[t]["amount_minor"]) for t in window["transaction_ids"]) == int(
        window["observations"]["window_minor"]
    )
    # rerun is idempotent: same snapshot, no duplicate alerts
    r = client.post("/api/v1/analysis/jobs", json={"dataset_id": ds_id})
    assert r.json()["id"] == job["id"]
    assert client.get("/api/v1/alerts", params={"dataset_id": ds_id, "limit": 200}).json()["total"] == len(alerts)


def test_lab_lists_composed_benchmark_suite(client):
    suites = {s["id"]: s for s in client.get("/api/v1/lab/suites").json()}
    assert "bench-v1" in suites and "S4_circular_flow" in suites["bench-v1"]["scenario_families"]


def test_evaluation_serves_artifact_and_hides_manifests(client, settings, tmp_path):
    artifact = {
        "schema_version": 1,
        "benchmark_version": "bench-harness-v1",
        "generated_at": "2026-11-17T12:00:00+00:00",
        "synthetic": True,
        "code": {"commit": "abc", "dirty": False, "dirty_paths": []},
        "environment": {"python": "3.13", "platform": "linux"},
        "generator": {"suite": "bench-v1", "version": "synthetic-bench-v1"},
        "config": {"detectors_version": "detectors-v2", "policy_version": "risk-policy-v2", "config_sha256": "f" * 64},
        "protocol": {
            "matching_rule": "m",
            "flagged": "f",
            "units": {"scenario": "s"},
            "splits": {"dev": "design"},
        },
        "splits": {
            "dev": {
                "seeds": [1000, 1001],
                "datasets": 2,
                "split_sha256": "a" * 64,
                "precision_mix": {"day": 2},
                "manifest": [{"seed": 1000}],
            }
        },
        "methods": [{"id": "nexora_v2", "label": "NEXORA v2", "description": "d"}],
        "results": {},
        "ablations": {},
        "runtime_seconds": 1.0,
        "limitations": ["synthetic"],
    }
    path = tmp_path / "bench.json"
    path.write_text(json.dumps(artifact))
    settings.benchmark_artifact = str(path)
    body = client.get("/api/v1/evaluation").json()
    assert body["splits"]["dev"]["role"] == "design" and "manifest" not in body["splits"]["dev"]
    assert body["synthetic"] is True and body["code"] == {"commit": "abc", "dirty": False}

    settings.benchmark_artifact = str(tmp_path / "missing.json")
    r = client.get("/api/v1/evaluation")
    assert r.status_code == 404 and r.json()["error"]["code"] == "BENCHMARK_NOT_FOUND"

    path.write_text(json.dumps({**artifact, "schema_version": 99}))
    settings.benchmark_artifact = str(path)
    r = client.get("/api/v1/evaluation")
    assert r.status_code == 500 and r.json()["error"]["code"] == "BENCHMARK_ARTIFACT_INVALID"


def test_downgrade_refuses_to_discard_published_v2_analyses(client, settings, db_url):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, text

    _create_and_analyse(client, settings, seed=1001, suite="bench-v1")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    with pytest.raises(Exception, match="ck_formations_kind"):
        command.downgrade(cfg, "0001")
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with create_engine(db_url).connect() as conn:  # transactional DDL: still at head, rows intact
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == head
        assert conn.execute(text("SELECT count(*) FROM formations WHERE kind = 'fan_out'")).scalar_one() > 0
