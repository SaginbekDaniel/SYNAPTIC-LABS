from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from secrets import token_urlsafe

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nexora.api.main import GATEWAY_TOKEN_HEADER, create_app
from nexora.settings import Settings

PATH = "/api/v1/demo/transfer-checks"
ANALYST_HEADER = "X-Nexora-Transfer-Analyst-Token"


def request_body(scenario_id: str, recipient: str | None = None) -> dict[str, str]:
    return {
        "scenario_id": scenario_id,
        "recipient_id": recipient or f"recipient-{scenario_id}",
        "currency": "KZT",
        "amount_minor": "15000000",
    }


@pytest.mark.parametrize(
    ("scenario", "recipient", "expected"),
    [
        ("regular", None, "ALLOW"),
        ("mule", None, "WARN"),
        ("merchant", None, "ALLOW"),
        ("limited", None, "LIMITED_SIGNAL"),
        ("review", None, "STEP_UP"),
        ("replay_early", "recipient-replay", "ALLOW"),
        ("replay_late", "recipient-replay", "STEP_UP"),
        ("timeout", None, "UNAVAILABLE"),
    ],
)
def test_demo_scenarios_are_deterministic_and_customer_data_is_minimal(
    scenario: str,
    recipient: str | None,
    expected: str,
) -> None:
    def no_session() -> None:
        raise AssertionError("transfer checks must not access the database")

    app = create_app()
    app.state.session_factory = no_session
    with TestClient(app) as client:
        response = client.post(PATH, json=request_body(scenario, recipient))
        assert response.status_code == 200
        body = response.json()
        assert body == client.post(PATH, json=request_body(scenario, recipient)).json()
        assert body["decision"] == expected
        assert body["simulation"] is True
        assert response.headers["cache-control"] == "no-store"
        assert set(body) == {
            "decision",
            "reason_codes",
            "customer_message",
            "risk_band",
            "coverage",
            "recommended_actions",
            "snapshot_id",
            "policy_version",
            "assessment_id",
            "simulation",
        }
        assert "demo-" not in response.text
        assert ("CONTINUE_SIMULATION" in body["recommended_actions"]) == (expected in {"ALLOW", "WARN"})


@pytest.mark.parametrize(
    ("values", "status"),
    [
        ({"amount_minor": "0"}, 422),
        ({"amount_minor": "1e5"}, 422),
        ({"amount_minor": 15000000}, 422),
        ({"amount_minor": "1" * 39}, 422),
        ({"currency": "USD"}, 422),
        ({"client_context": "fabricated"}, 422),
        ({"as_of": "2099-01-01T00:00:00Z"}, 422),
        ({"sender_id": "other"}, 422),
        ({"recipient_id": "recipient-review"}, 404),
        ({"scenario_id": "other"}, 404),
    ],
)
def test_request_validation(values: dict[str, object], status: int) -> None:
    with TestClient(create_app()) as client:
        response = client.post(PATH, json={**request_body("mule"), **values})
        assert response.status_code == status


def test_investigation_requires_gateway_and_analyst_access_and_matching_assessment() -> None:
    gateway, analyst = token_urlsafe(32), token_urlsafe(32)
    app = create_app(Settings(gateway_token=gateway, transfer_analyst_token=SecretStr(analyst)))
    gateway_headers = {GATEWAY_TOKEN_HEADER: gateway}
    analyst_headers = {**gateway_headers, ANALYST_HEADER: analyst}
    with TestClient(app) as client:
        assert client.get(f"{PATH}/scenarios").status_code == 401
        assert len(client.get(f"{PATH}/scenarios", headers=gateway_headers).json()) == 8
        check = request_body("replay_late", "recipient-replay")
        result = client.post(PATH, headers=gateway_headers, json=check).json()
        selection = {"assessment_id": result["assessment_id"], "check": check}
        assert client.post(f"{PATH}/evidence", json=selection, headers={ANALYST_HEADER: analyst}).status_code == 401
        for headers in (gateway_headers, {**gateway_headers, ANALYST_HEADER: "invalid"}):
            denied = client.post(f"{PATH}/evidence", json=selection, headers=headers)
            assert denied.status_code == 403
            assert denied.json()["error"]["code"] == "TRANSFER_ANALYST_ACCESS_REQUIRED"
        changed = {**selection, "check": {**check, "amount_minor": "1"}}
        assert client.post(f"{PATH}/evidence", json=changed, headers=analyst_headers).status_code == 404
        response = client.post(f"{PATH}/evidence", json=selection, headers=analyst_headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        evidence = response.json()
        assert evidence["snapshot_id"] == result["snapshot_id"]
        assert evidence["policy_version"] == result["policy_version"]
        txs = {tx["id"]: tx for tx in evidence["transactions"]}
        assert all(
            reference in txs
            for formation in evidence["formations"]
            for indicator in formation["indicators"]
            for reference in indicator["transaction_ids"]
        )
        cutoff = datetime.fromisoformat(evidence["as_of"])
        assert all(datetime.fromisoformat(tx["ingested_at"]) <= cutoff for tx in txs.values())
        assert any(tx["ingested_at"][:10] > tx["occurred_at"][:10] for tx in txs.values())


def test_no_token_and_kill_switch_fail_closed() -> None:
    app = create_app(Settings(transfer_protection_enabled=False, transfer_analyst_token=SecretStr("")))
    with TestClient(app) as client:
        check = request_body("review")
        result = client.post(PATH, json=check).json()
        assert result["decision"] == "UNAVAILABLE"
        assert result["reason_codes"] == ["FEATURE_DISABLED"]
        response = client.post(f"{PATH}/evidence", json={"check": check, "assessment_id": result["assessment_id"]})
        assert response.status_code == 403
        assert client.get("/health/live").status_code == 200


def test_dependency_failure_and_missing_profile_are_distinguished() -> None:
    app = create_app()
    with TestClient(app) as client:
        service = app.state.transfer_demo
        app.state.transfer_demo = replace(service, profiles=None)
        check = request_body("mule")
        assert client.post(PATH, json=check).json()["reason_codes"] == ["DEPENDENCY_FAILURE"]
        app.state.transfer_demo = replace(service, profiles={})
        assert client.post(PATH, json=check).json()["reason_codes"] == ["MISSING_PROFILE"]
        app.state.transfer_demo = replace(service, graph_config_sha256="incompatible")
        result = client.post(PATH, json=check).json()
        assert result["reason_codes"] == ["DEPENDENCY_FAILURE"]
        assert result["snapshot_id"] is None
