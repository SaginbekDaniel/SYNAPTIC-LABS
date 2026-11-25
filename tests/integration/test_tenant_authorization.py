from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nexora.api.identity import LocalTokenVerifier, Principal
from nexora.api.main import create_app
from nexora.domain.ids import sha256_hex
from nexora.persistence.db import session_factory
from nexora.worker.runner import drain

ROOT = "/api/v1"


def claims(name):
    return {"Authorization": f"Bearer {name}-local-fixture-token-at-least-32"}


def test_analytics_permissions_and_object_reads_are_tenant_scoped(settings):
    identities = {
        "left": Principal(subject="left-analyst", tenant="org-left", role="analyst"),
        "reviewer": Principal(subject="left-reviewer", tenant="org-left", role="reviewer"),
        "right": Principal(subject="right-analyst", tenant="org-right", role="analyst"),
        "customer": Principal(subject="customer", tenant="org-left", role="customer"),
        "service": Principal(subject="service-batch", tenant="org-left", role="service"),
    }
    verifier = LocalTokenVerifier({sha256_hex(claims(key)["Authorization"][7:]): v for key, v in identities.items()})
    secured = settings.model_copy(update={"authenticated_analytics": True})
    with TestClient(create_app(secured, identity_verifier=verifier)) as client:
        assert client.get(f"{ROOT}/datasets").status_code == 401
        assert client.get(f"{ROOT}/datasets").headers["www-authenticate"] == "Bearer"
        assert client.get(f"{ROOT}/datasets", headers=claims("customer")).status_code == 403
        fixture = {"suite": "demo-v1", "seed": 2026}
        assert client.post(f"{ROOT}/lab/datasets", headers=claims("service"), json=fixture).status_code == 403
        left = client.post(f"{ROOT}/lab/datasets", json=fixture, headers=claims("left")).json()["dataset"]["id"]
        right = client.post(f"{ROOT}/lab/datasets", json=fixture, headers=claims("right")).json()["dataset"]["id"]
        listing = client.get(f"{ROOT}/datasets", headers=claims("right")).json()
        assert {row["id"] for row in listing["items"]} == {right}
        assert client.get(f"{ROOT}/datasets/{left}", headers=claims("right")).status_code == 404
        key = str(uuid4())
        job_path = f"{ROOT}/analysis/jobs"
        assert client.post(job_path, json={"dataset_id": left}, headers=claims("right")).status_code == 404
        job = client.post(job_path, json={"dataset_id": left, "idempotency_key": key}, headers=claims("left"))
        other = client.post(job_path, json={"dataset_id": right, "idempotency_key": key}, headers=claims("right"))
        assert job.status_code == other.status_code == 202
        assert client.get(job.headers["Location"], headers=claims("right")).status_code == 404
        drain(session_factory(settings.database_url))
        snapshot = client.get(job.headers["Location"], headers=claims("left")).json()["snapshot_id"]
        assert client.get(f"{ROOT}/analysis/snapshots/{snapshot}", headers=claims("right")).status_code == 404
        rows = client.get(f"{ROOT}/alerts", params={"dataset_id": left}, headers=claims("left")).json()["items"]
        assert rows
        alert = rows[0]["id"]
        assert client.get(f"{ROOT}/alerts/{alert}/evidence", headers=claims("right")).status_code == 404
        assert client.get(f"{ROOT}/alerts", params={"dataset_id": left}, headers=claims("right")).json()["total"] == 0
        case_body = {"alert_id": alert}
        assert client.post(f"{ROOT}/cases", json=case_body, headers=claims("right")).status_code == 404
        case = client.post(f"{ROOT}/cases", json=case_body, headers=claims("left")).json()
        path = f"{ROOT}/cases/{case['id']}"
        assert case["assigned_to"] == "left-analyst"
        assert client.get(f"{path}/audit", headers=claims("right")).status_code == 404
        assert client.post(f"{path}/notes", json={"body": "review note"}, headers=claims("right")).status_code == 404
        started = {"to_status": "investigating", "expected_version": 1}
        assert client.post(f"{path}/decisions", json=started, headers=claims("left")).status_code == 200
        escalation = {"to_status": "escalated", "expected_version": 2, "reason": "Synthetic evidence"}
        assert client.post(f"{path}/decisions", json=escalation, headers=claims("left")).status_code == 403
        assert client.post(f"{path}/decisions", json=escalation, headers=claims("reviewer")).status_code == 200
        trail = client.get(f"{path}/audit", headers=claims("reviewer")).json()
        assert trail[-1]["actor"] == "left-reviewer"

    with TestClient(create_app(settings)) as demo:
        assert demo.get(f"{ROOT}/datasets/{left}").status_code == 404


def test_deployed_and_production_profiles_fail_closed(settings):
    with pytest.raises(ValueError, match="gateway authentication"):
        create_app(settings.model_copy(update={"execution_profile": "deployed_demo"}))
    with pytest.raises(ValueError, match="analyst evidence provisioning"):
        create_app(
            settings.model_copy(
                update={
                    "execution_profile": "deployed_demo",
                    "gateway_token": "g" * 32,
                    "expose_api_docs": False,
                }
            )
        )
    with pytest.raises(ValueError, match="external identity verifier"):
        create_app(
            settings.model_copy(
                update={
                    "execution_profile": "production",
                    "gateway_token": "g" * 32,
                    "expose_api_docs": False,
                }
            )
        )


def test_reviewed_feedback_is_independent_versioned_scoped_and_pseudonymous(settings):
    from pydantic import SecretStr

    identities = {
        "analyst": Principal(subject="fixture-analyst", tenant="feedback-left", role="analyst"),
        "decider": Principal(subject="fixture-decider", tenant="feedback-left", role="reviewer"),
        "reviewer": Principal(subject="fixture-reviewer", tenant="feedback-left", role="reviewer"),
        "other": Principal(subject="fixture-other", tenant="feedback-right", role="reviewer"),
    }
    verifier = LocalTokenVerifier({sha256_hex(claims(key)["Authorization"][7:]): v for key, v in identities.items()})
    secured = settings.model_copy(update={"authenticated_analytics": True, "feedback_export_key": SecretStr("f" * 32)})
    analyst, decider, reviewer, other = [claims(name) for name in identities]
    with TestClient(create_app(secured, identity_verifier=verifier)) as client:
        fixture = {"suite": "demo-v1", "seed": 2026}
        seeded = client.post(f"{ROOT}/lab/datasets", json=fixture, headers=analyst)
        dataset = seeded.json()["dataset"]["id"]
        assert client.post(f"{ROOT}/analysis/jobs", json={"dataset_id": dataset}, headers=analyst).status_code == 202
        drain(session_factory(settings.database_url))
        alert = client.get(f"{ROOT}/alerts", params={"dataset_id": dataset}, headers=analyst).json()["items"][0]
        case = client.post(f"{ROOT}/cases", json={"alert_id": alert["id"]}, headers=analyst).json()
        path = f"{ROOT}/cases/{case['id']}"
        assert client.get(f"{path}/feedback-label", headers=reviewer).status_code == 404
        transition = f"{path}/decisions"
        assert (
            client.post(
                transition, json={"to_status": "investigating", "expected_version": 1}, headers=analyst
            ).status_code
            == 200
        )
        decision = {"to_status": "escalated", "expected_version": 2, "reason": "Requires disposition"}
        assert client.post(transition, json=decision, headers=decider).status_code == 200

        body = {
            "expected_case_version": 3,
            "expected_alert_revision": alert["revision"],
            "outcome": "confirmed_fraud",
            "reason": "Independent synthetic adjudication",
        }
        route = f"{path}/feedback"
        assert client.post(route, json=body, headers=analyst).status_code == 403
        assert client.post(route, json=body, headers=other).status_code == 404
        assert client.post(route, json=body, headers=decider).status_code == 409
        approved = client.post(route, json=body, headers=reviewer)
        assert approved.status_code == 201
        label = client.get(f"{path}/feedback-label", headers=reviewer)
        assert label.status_code == 200
        assert label.json() == {
            "version": "feedback-v1",
            "sample_ref": label.json()["sample_ref"],
            "label": "confirmed_fraud",
            "quality": "independently_reviewed",
            "policy_version": "risk-policy-v2",
        }
        assert len(label.json()["sample_ref"]) == 64
        assert case["id"] not in label.text and "fixture-" not in label.text and "adjudication" not in label.text
        assert client.get(f"{path}/feedback-label", headers=other).status_code == 404
        assert client.post(route, json=body, headers=reviewer).status_code == 409
        body.update(outcome="insufficient_evidence", expected_review_id=approved.json()["review_id"])
        assert client.post(route, json=body, headers=reviewer).status_code == 201
        assert client.get(f"{path}/feedback-label", headers=reviewer).status_code == 409
        events = client.get(f"{path}/audit", headers=reviewer).json()
        assert [event["action"] for event in events[-2:]] == ["case.feedback_reviewed"] * 2
        assert all(event["actor"] == "fixture-reviewer" for event in events[-2:])
        assert events[-2]["after"]["snapshot_id"] == events[-1]["after"]["snapshot_id"]
