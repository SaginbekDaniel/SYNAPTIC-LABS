from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient

from nexora.api.identity import LocalTokenVerifier, Principal
from nexora.api.main import create_app
from nexora.domain.ids import sha256_hex

PATH = "/api/v1/sandbox/transfers"
EARLY = "2026-10-20T12:00:00Z"
LATE = "2026-10-23T12:00:00Z"


def auth(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {name}-synthetic-token-for-local-test-only"}


def app_client(settings):
    accounts = {
        "customer": Principal(subject="customer-1", tenant="alpha", role="customer", customer_ref="demo-sender"),
        "peer": Principal(subject="customer-2", tenant="alpha", role="customer", customer_ref="demo-sender"),
        "reviewer": Principal(subject="reviewer-1", tenant="alpha", role="reviewer"),
        "analyst": Principal(subject="analyst-1", tenant="alpha", role="analyst"),
        "outsider": Principal(subject="reviewer-2", tenant="beta", role="reviewer"),
    }
    verifier = LocalTokenVerifier(
        {sha256_hex(auth(name)["Authorization"][7:]): user for name, user in accounts.items()}
    )
    return TestClient(create_app(settings, identity_verifier=verifier))


def intent(beneficiary="demo-replay", requested_at=LATE):
    return {
        "intent_id": str(uuid4()),
        "beneficiary": beneficiary,
        "amount_minor": "9800000",
        "currency": "KZT",
        "requested_at": requested_at,
    }


def act(client, uri, name, action, *, action_id=None):
    return client.post(
        f"{uri}/actions",
        headers=auth(name),
        json={"action_id": action_id or str(uuid4()), "action": action},
    )


def test_point_in_time_evidence_and_idempotent_sandbox_actions_survive_restart(settings):
    first, last = intent(requested_at=EARLY), intent()
    with app_client(settings) as client:
        assert client.post(PATH, json=last).status_code == 401
        assert client.post(PATH, json=last, headers=auth("reviewer")).status_code == 403
        early = client.post(PATH, json=first, headers=auth("customer")).json()
        response = client.post(PATH, json=last, headers=auth("customer"))
        assert response.status_code == 201, response.text
        late = response.json()
        assert (early["decision"], late["decision"], late["status"]) == ("ALLOW", "STEP_UP", "STEP_UP_REQUIRED")
        path = f"{PATH}/{late['assessment_id']}"
        assert act(client, path, "customer", "CONFIRM").status_code == 409
        assert act(client, path, "customer", "VERIFY_STEP_UP").status_code == 403
        assert act(client, path, "analyst", "VERIFY_STEP_UP").status_code == 403
        assert act(client, path, "outsider", "VERIFY_STEP_UP").status_code == 404
        assert act(client, path, "reviewer", "VERIFY_STEP_UP").json()["to_status"] == "READY"
        action_id = str(uuid4())
        acknowledgement = act(client, path, "customer", "CONFIRM", action_id=action_id)
        assert acknowledgement.json()["to_status"] == "SIMULATED_COMPLETED"
        assert acknowledgement.json()["simulation"] is True
        assert act(client, path, "customer", "CONFIRM", action_id=action_id).json() == acknowledgement.json()

    with app_client(settings) as restarted:
        assert restarted.get(path, headers=auth("peer")).status_code == 404
        assert restarted.get(path, headers=auth("outsider")).status_code == 404
        assert restarted.get(f"{path}/evidence", headers=auth("customer")).status_code == 403
        assert restarted.get(f"{path}/evidence", headers=auth("outsider")).status_code == 404
        evidence = restarted.get(f"{path}/evidence", headers=auth("analyst"))
        assert evidence.status_code == 200
        assert evidence.json()["assessment"]["policy_version"] == late["policy_version"]
        assert evidence.json()["profile"]["snapshot_id"] == late["snapshot_id"]
        assert len(restarted.get(f"{path}/actions", headers=auth("reviewer")).json()) == 2
        assert (
            restarted.post(PATH, headers=auth("customer"), json=last).json()["assessment_id"] == late["assessment_id"]
        )
        assert restarted.post(PATH, headers=auth("customer"), json=last | {"amount_minor": "1"}).status_code == 409


def test_timeout_stays_unavailable_and_linked_retry_is_a_separate_assessment(settings):
    with app_client(settings) as client:
        response = client.post(PATH, headers=auth("customer"), json=intent("demo-timeout"))
        assert response.status_code == 201
        saved = response.json()
        assert (saved["decision"], saved["status"]) == ("UNAVAILABLE", "UNAVAILABLE")
        path = f"{PATH}/{saved['assessment_id']}"
        assert act(client, path, "customer", "CONFIRM").status_code == 409
        retry = intent("demo-timeout") | {"supersedes_assessment_id": saved["assessment_id"]}
        assert client.post(PATH, headers=auth("peer"), json=retry).status_code == 404
        repeated = client.post(PATH, headers=auth("customer"), json=retry).json()
        assert repeated["assessment_id"] != saved["assessment_id"]
        assert client.get(path, headers=auth("customer")).json() == saved


def test_concurrent_intent_and_action_replays_have_one_effect(settings):
    data = intent(requested_at=EARLY)
    with app_client(settings) as client, ThreadPoolExecutor(max_workers=6) as pool:
        replies = list(pool.map(lambda _: client.post(PATH, headers=auth("customer"), json=data), range(6)))
        assert {response.status_code for response in replies} == {201}
        assert len({response.json()["assessment_id"] for response in replies}) == 1
        path = f"{PATH}/{replies[0].json()['assessment_id']}"
        action_id = str(uuid4())
        actions = list(pool.map(lambda _: act(client, path, "customer", "CONFIRM", action_id=action_id), range(6)))
        assert {response.status_code for response in actions} == {200}
        assert all(response.json() == actions[0].json() for response in actions)
        assert len(client.get(f"{path}/actions", headers=auth("customer")).json()) == 1
