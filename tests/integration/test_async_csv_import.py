from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from nexora.api.main import create_app
from nexora.persistence import orm
from nexora.persistence.db import session_scope
from nexora.worker.runner import run_once

CSV = (
    b"source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,observed_date\n"
    b"ok,a,b,9007199254740993,KZT,2026-11-20\n"
    b"bad,b,d,-5,KZT,2026-11-20\n"
)
PATH = "/api/v1/datasets/import-jobs"


def submit(client, name, key, *, csv=CSV, path=PATH):
    return client.post(path, data={"name": name}, files={"file": ("sample.csv", csv)}, headers={"Idempotency-Key": key})


def test_async_upload_is_durable_atomic_and_shares_sync_idempotency(client, factory, settings):
    name, key = str(uuid4()), str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as workers:
        requests = list(workers.map(lambda _: submit(client, name, key), range(4)))
    assert all(response.status_code == 202 for response in requests)
    assert len({response.json()["id"] for response in requests}) == 1
    initial = requests[0].json()
    path = requests[0].headers["Location"]
    assert initial["status"] == "accepted" and initial["result"] is None
    with session_scope(factory) as session:
        assert session.scalar(select(orm.Dataset).where(orm.Dataset.name == name)) is None
    assert run_once(factory) == UUID(initial["id"])
    with TestClient(create_app(settings)) as restarted:
        after = restarted.get(path).json()
        assert after["status"] == "completed" and after["attempt_count"] == 1
        assert after["result"]["report"]["accepted"] == after["result"]["report"]["quarantined"] == 1
        assert submit(restarted, name, key, path="/api/v1/datasets/import").json() == after["result"]
        assert submit(restarted, name, key, csv=b"different").status_code == 409
    with session_scope(factory) as session:
        dataset = UUID(after["result"]["dataset"]["id"])
        transfer = session.scalars(select(orm.Transaction).where(orm.Transaction.dataset_id == dataset)).one()
        assert int(transfer.amount_minor) == 9007199254740993
        assert session.get_one(orm.CsvImportJob, UUID(initial["id"])).content is None


def test_async_import_recovers_expired_lease_and_does_not_publish_invalid_files(client, factory):
    response = submit(client, str(uuid4()), str(uuid4()))
    job_id = UUID(response.json()["id"])
    with session_scope(factory) as session:
        session.execute(
            update(orm.CsvImportJob)
            .where(orm.CsvImportJob.id == job_id)
            .values(
                status="processing",
                attempt_count=1,
                lease_until=text("now() - interval '1 minute'"),
            )
        )
    assert run_once(factory) == job_id
    recovered = client.get(response.headers["Location"]).json()
    assert (recovered["status"], recovered["attempt_count"]) == ("completed", 2)

    name = str(uuid4())
    response = submit(client, name, str(uuid4()), csv=b"invalid\n")
    assert run_once(factory) == UUID(response.json()["id"])
    failed = client.get(response.headers["Location"]).json()
    assert (failed["status"], failed["error_code"], failed["result"]) == ("failed", "CSV_SCHEMA_INVALID", None)
    with session_scope(factory) as session:
        assert session.scalar(select(orm.Dataset).where(orm.Dataset.name == name)) is None
        assert session.get_one(orm.CsvImportJob, UUID(failed["id"])).content is None


def test_accepted_import_can_be_cancelled_without_dataset(client, factory):
    response = submit(client, str(uuid4()), str(uuid4()))
    uri = response.headers["Location"]
    answer = client.post(f"{uri}/cancel")
    assert answer.status_code == 200
    assert answer.json()["status"] == "cancelled"
    assert client.post(f"{uri}/cancel").json() == answer.json()
    assert run_once(factory) is None
