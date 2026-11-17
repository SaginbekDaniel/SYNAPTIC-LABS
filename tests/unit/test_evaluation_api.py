"""Evaluation endpoints serve recorded benchmark artifacts only — never computed or invented numbers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nexora.api.main import create_app
from nexora.settings import Settings, get_settings

REPO_RESULTS = Path(__file__).resolve().parents[2] / "benchmarks" / "results"


def client_for(results_dir: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(benchmark_results_dir=str(results_dir))
    return TestClient(app)


def test_no_recorded_run_is_an_explicit_404(tmp_path: Path) -> None:
    r = client_for(tmp_path).get("/api/v1/evaluation/runs")
    assert r.status_code == 404 and r.json()["error"]["code"] == "BENCHMARK_NOT_RUN"


def test_recorded_runs_validate_against_the_contract() -> None:
    client = client_for(REPO_RESULTS)
    runs = client.get("/api/v1/evaluation/runs").json()
    assert runs["latest"] and runs["runs"]
    for ref in runs["runs"]:
        r = client.get(f"/api/v1/evaluation/runs/{ref['label']}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "SYNTHETIC" in body["disclaimer"]
        raw = json.loads((REPO_RESULTS / ref["label"] / "report.json").read_text())
        # numbers are passed through unchanged from the artifact
        split, method = next(iter(raw["results"].items()))
        name, metrics = next(iter(method.items()))
        served = next(x for x in body["results"] if x["split"] == split and x["method"] == name)
        assert served["scenario"]["tp"] == metrics["unit_scenario"]["tp"]
        assert served["scenario"]["precision"] == metrics["unit_scenario"]["precision"]


@pytest.mark.parametrize("label", ["nope", "..", "a b", "x" * 65])
def test_unknown_or_unsafe_labels_are_rejected(label: str) -> None:
    r = client_for(REPO_RESULTS).get(f"/api/v1/evaluation/runs/{label}")
    assert r.status_code in (404, 422)


def test_index_entry_cannot_escape_results_dir(tmp_path: Path) -> None:
    (tmp_path / "index.json").write_text(
        json.dumps({"runs": [{"label": "x", "created_at": "t", "path": "../../etc/passwd"}]})
    )
    r = client_for(tmp_path).get("/api/v1/evaluation/runs/x")
    assert r.status_code == 404 and r.json()["error"]["code"] == "BENCHMARK_RUN_NOT_FOUND"
