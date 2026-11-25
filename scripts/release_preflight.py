"""Run a synthetic release preflight on an isolated loopback stack and print JSON."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from nexora.persistence.health import release_heads

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "audit" / "remediation" / "fixtures"
API = "/api/v1"
TRANSFER = f"{API}/sandbox/transfers"
DEMO = f"{API}/demo/transfer-checks"


class PreflightError(Exception):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PreflightError(code)


def wait_for(client: httpx.Client, path: str, success: str, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(path)
        require(response.status_code == 200, "POLL_FAILED")
        body = response.json()
        if body["status"] == success:
            return body
        require(body["status"] not in {"failed", "cancelled"}, "WORKER_TERMINAL_FAILURE")
        time.sleep(0.15)
    raise PreflightError("WORKER_TIMEOUT")


def run(args) -> dict:
    for url in (args.api, args.web):
        parsed = urlparse(url)
        require(parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}, "LOOPBACK_ONLY")
        require(not parsed.username and not parsed.password, "URL_CREDENTIALS_FORBIDDEN")
    required = (
        "NEXORA_GATEWAY_TOKEN",
        "NEXORA_TRANSFER_ANALYST_TOKEN",
        "NEXORA_PREFLIGHT_CUSTOMER",
        "NEXORA_PREFLIGHT_REVIEWER",
    )
    require(all(len(os.environ.get(key, "")) >= 32 for key in required), "PREFLIGHT_CREDENTIALS_MISSING")
    gateway, analyst, customer, reviewer = (os.environ[key] for key in required)
    results: list[dict] = []
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(commit == args.expected_commit, "UNEXPECTED_COMMIT")
    results.append({"check": "git_head", "commit": commit})
    deps = {name: importlib.metadata.version(name) for name in ("fastapi", "sqlalchemy", "psycopg", "alembic")}
    npm = subprocess.run(["npm", "ls", "--depth=0", "--prefix", "apps/web"], cwd=ROOT, capture_output=True)
    require(npm.returncode == 0, "FRONTEND_DEPENDENCY_CHECK_FAILED")
    results.append({"check": "dependencies", "python": deps, "web": "npm ls passed"})

    base_headers = {"X-Nexora-Gateway-Token": gateway}

    def bearer(token: str) -> dict:
        return base_headers | {"Authorization": f"Bearer {token}"}

    with httpx.Client(base_url=args.api, headers=base_headers, trust_env=False, timeout=8) as api:

        def checked(method, path, status, **options):
            response = api.request(method, path, **options)
            require(response.status_code == status, f"EXPECTED_{status}_GOT_{response.status_code}")
            return response

        health = checked("GET", "/health/ready", 200).json()
        require(health["database"] and health["schema"] == "compatible", "DATABASE_OR_SCHEMA_UNAVAILABLE")
        require(health["expected_migrations"] == list(release_heads()), "RELEASE_SCHEMA_MISMATCH")
        checked("GET", "/health/live", 200)
        with httpx.Client(base_url=args.api, trust_env=False, timeout=5) as direct:
            require(direct.get(f"{API}/datasets").status_code == 401, "API_GATEWAY_AUTH_MISSING")
        web = httpx.get(args.web, follow_redirects=True, trust_env=False, timeout=5)
        require(web.status_code == 200 and "<html" in web.text.lower(), "FRONTEND_UNAVAILABLE")
        results.append({"check": "health_gateway_frontend", "schema": health["migration"]})

        cases = []
        for name, predicted in (("suspicious-network", True), ("verified-settlement", False)):
            start = time.perf_counter()
            document = (FIXTURES / f"{name}.csv").read_bytes()
            upload = checked(
                "POST",
                f"{API}/datasets/import-jobs",
                202,
                data={"name": f"{name}-{uuid4()}"},
                files={"file": (f"{name}.csv", document, "text/csv")},
            )
            accepted_ms = (time.perf_counter() - start) * 1000
            finished = wait_for(api, upload.headers["location"], "completed")
            imported = finished["result"]
            require(imported["report"]["accepted"] == 3, "UNEXPECTED_IMPORT_REPORT")
            dataset = imported["dataset"]["id"]
            job = checked(
                "POST", f"{API}/analysis/jobs", 202, json={"dataset_id": dataset, "profile": "experimental_context"}
            )
            analysis = wait_for(api, job.headers["location"], "succeeded")
            alerts = checked("GET", f"{API}/alerts", 200, params={"dataset_id": dataset}).json()
            require(bool(alerts["total"]) == predicted, "CONTEXT_SCENARIO_EXPECTATION_FAILED")
            case = {
                "dataset": name,
                "alerts": alerts["total"],
                "accepted_ms": accepted_ms,
                "snapshot_id": analysis["snapshot_id"],
            }
            if predicted:
                alert = alerts["items"][0]["id"]
                evidence = checked("GET", f"{API}/alerts/{alert}/evidence", 200).json()
                require(len(evidence["transactions"]) == 3, "UNEXPECTED_ALERT_EVIDENCE")
                opened = checked("POST", f"{API}/cases", 201, json={"alert_id": alert}).json()
                case_path = f"{API}/cases/{opened['id']}"
                checked(
                    "POST", f"{case_path}/decisions", 200, json={"to_status": "investigating", "expected_version": 1}
                )
                require(len(checked("GET", f"{case_path}/audit", 200).json()) == 2, "CASE_AUDIT_INCOMPLETE")
                case["case_audit_events"] = 2
            cases.append(case)
        results.append({"check": "csv_worker_context_cases", "fixtures": cases})

        legacy_check = {
            "scenario_id": "replay_late",
            "recipient_id": "recipient-replay",
            "amount_minor": "9800000",
            "currency": "KZT",
        }
        legacy = checked("POST", DEMO, 200, json=legacy_check).json()
        evidence_request = {"assessment_id": legacy["assessment_id"], "check": legacy_check}
        checked("POST", f"{DEMO}/evidence", 403, json=evidence_request)
        checked(
            "POST",
            f"{DEMO}/evidence",
            200,
            json=evidence_request,
            headers=base_headers | {"X-Nexora-Transfer-Analyst-Token": analyst},
        )
        results.append({"check": "demo_analyst_scope", "authorized": 200, "unauthorized": 403})

        def intent(recipient, timepoint):
            return {
                "intent_id": str(uuid4()),
                "beneficiary": recipient,
                "currency": "KZT",
                "amount_minor": "9800000",
                "requested_at": timepoint,
            }

        early = "2026-10-20T12:00:00Z"
        late = "2026-10-23T12:00:00Z"
        payload = intent("demo-replay", late)
        ordered = [
            checked("POST", TRANSFER, 201, json=data, headers=bearer(customer)).json()
            for data in (intent("demo-replay", early), payload, intent("demo-timeout", late))
        ]
        require([row["decision"] for row in ordered] == ["ALLOW", "STEP_UP", "UNAVAILABLE"], "TRANSFER_REPLAY_FAILED")
        review_path = f"{TRANSFER}/{ordered[1]['assessment_id']}"
        checked("GET", f"{review_path}/evidence", 403, headers=bearer(customer))
        checked("GET", f"{review_path}/evidence", 200, headers=bearer(reviewer))
        repeated = checked("POST", TRANSFER, 201, json=payload, headers=bearer(customer)).json()
        require(repeated["assessment_id"] == ordered[1]["assessment_id"], "TRANSFER_REPLAY_DUPLICATED")
        action = {"action_id": str(uuid4()), "action": "VERIFY_STEP_UP"}
        verified = checked("POST", f"{review_path}/actions", 200, headers=bearer(reviewer), json=action).json()
        require(verified["to_status"] == "READY", "STEP_UP_NOT_ACKNOWLEDGED")
        confirmation = {"action_id": str(uuid4()), "action": "CONFIRM"}
        ack = checked("POST", f"{review_path}/actions", 200, headers=bearer(customer), json=confirmation).json()
        require(ack["simulation"] and ack["to_status"] == "SIMULATED_COMPLETED", "SANDBOX_ACTION_NOT_ACKNOWLEDGED")
        again = checked("POST", f"{review_path}/actions", 200, headers=bearer(customer), json=confirmation).json()
        require(again == ack, "SANDBOX_ACTION_DUPLICATED")
        stopped = f"{TRANSFER}/{ordered[2]['assessment_id']}/actions"
        checked("POST", stopped, 409, headers=bearer(customer), json=confirmation)
        results.append(
            {
                "check": "sandbox_persistence_and_failure",
                "decisions": [r["decision"] for r in ordered],
                "acknowledgement": ack["to_status"],
                "replay_idempotent": True,
            }
        )
    return {"passed": True, "checks": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--web", default="http://127.0.0.1:5173")
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        report = run(args)
    except PreflightError as exc:
        report = {"passed": False, "failure": str(exc)}
    except (httpx.HTTPError, ValueError, KeyError, OSError):
        report = {"passed": False, "failure": "SERVICE_OR_CONFIGURATION_ERROR"}
    print(json.dumps(report, indent=2))
    return int(not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
