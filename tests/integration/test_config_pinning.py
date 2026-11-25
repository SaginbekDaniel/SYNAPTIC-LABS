import json
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from nexora.analytics.config import default_config, experimental_config
from nexora.api.main import create_app
from nexora.domain.ids import sha256_hex
from nexora.persistence import orm
from nexora.persistence.db import session_scope
from nexora.worker.runner import run_once

FILE = (
    b"source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,occurred_at\n"
    b"ab,a,b,8000000,KZT,2026-11-01T12:00:00Z\n"
    b"bc,b,c,8000000,KZT,2026-11-02T12:00:00Z\n"
    b"cd,c,d,8000000,KZT,2026-11-03T12:00:00Z\n"
)


def test_csv_context_is_pinned_with_the_job_and_preserves_ledger_evidence(settings, factory, tmp_path):
    path = tmp_path / "trusted.json"
    path.write_text(
        json.dumps(
            {
                f"demo:{sha256_hex(FILE)}": {
                    "as_of": "2026-11-11T00:00:00Z",
                    "facts": [
                        {
                            "source_ref": "fixture-settlement",
                            "kind": "verified_business_activity",
                            "subject": "d",
                            "currency": "KZT",
                            "observed_at": "2026-11-03T12:01:00Z",
                            "known_at": "2026-11-04T00:00:00Z",
                            "valid_until": "2026-11-18T00:00:00Z",
                            "source_transaction_ids": ["ab", "bc", "cd"],
                        }
                    ],
                },
            }
        )
    )
    configured = settings.model_copy(update={"verified_context_catalog": str(path)})
    with TestClient(create_app(configured)) as client:
        imported = client.post(
            "/api/v1/datasets/import", data={"name": str(uuid4())}, files={"file": ("fixture.csv", FILE)}
        )
        assert imported.status_code == 201
        dataset = imported.json()["dataset"]["id"]
        uri = "/api/v1/analysis/jobs"
        key = str(uuid4())
        v3 = client.post(uri, json={"dataset_id": dataset, "profile": "experimental_context", "idempotency_key": key})
        assert v3.status_code == 202
        assert client.post(uri, json={"dataset_id": dataset, "idempotency_key": key}).status_code == 409
        # Existing queued inputs are independent of later edits to the source catalog.
        path.write_text("{}")
        job_id = UUID(v3.json()["id"])
        assert run_once(factory, config=default_config()) == job_id
        status = client.get(v3.headers["Location"]).json()
        assert status["status"] == "succeeded"
        assert client.get("/api/v1/alerts", params={"dataset_id": dataset}).json()["total"] == 0
        with session_scope(factory) as session:
            snapshot_id = UUID(status["snapshot_id"])
            snapshot = session.get_one(orm.GraphSnapshot, snapshot_id)
            formation = session.scalars(select(orm.Formation).where(orm.Formation.snapshot_id == snapshot_id)).one()
            assessment = session.scalars(
                select(orm.RiskAssessmentRow).where(orm.RiskAssessmentRow.formation_id == formation.id)
            ).one()
            assert snapshot.config_sha256 == experimental_config().config_sha256
            assert assessment.band == "low"
            assert "CONTEXT_VERIFIED_BUSINESS_ACTIVITY" in {reason["code"] for reason in assessment.reason_codes}
