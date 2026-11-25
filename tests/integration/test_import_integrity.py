from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from nexora.api.main import create_app
from nexora.persistence import orm
from nexora.persistence.db import session_scope

COLUMNS = "source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,observed_date"
ROW = "t1,source-a,source-b,9007199254740993,KZT,2026-01-01"
CSV = f"{COLUMNS}\n{ROW}\n".encode()
ENDPOINT = "/api/v1/datasets/import"


def upload(client, name, *, content=CSV, key=None, boundary=""):
    return client.post(
        ENDPOINT,
        data={"name": name, "boundary_account_ids": boundary},
        files={"file": ("fixture.csv", content, "text/csv")},
        headers={} if key is None else {"Idempotency-Key": key},
    )


@pytest.mark.parametrize("duplicate", ["amount_minor", " amount_minor ", "AMOUNT_MINOR", " AMOUNT_MINOR "])
def test_ambiguous_headers_are_rejected_without_writes(client, factory, duplicate):
    name = str(uuid4())
    csv = f"\ufeff{COLUMNS},{duplicate}\n{ROW},1\n".encode()
    response = upload(client, name, content=csv)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CSV_SCHEMA_INVALID"
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(orm.Dataset).where(orm.Dataset.name == name)) == 0


def test_normalized_headers_preserve_exact_amount(client, factory):
    csv = f"\ufeff{COLUMNS.upper().replace(',', ', ')}\r\n{ROW}\r\n".encode()
    dataset = UUID(upload(client, str(uuid4()), content=csv).json()["dataset"]["id"])
    with session_scope(factory) as session:
        assert session.scalar(select(orm.Transaction.amount_minor).where(orm.Transaction.dataset_id == dataset)) == (
            9007199254740993
        )


def test_parallel_csv_import_replays_transactionally(client, factory, settings):
    name, key = str(uuid4()), str(uuid4())

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: upload(client, name, key=key), range(6)))

    assert [result.status_code for result in results] == [201] * 6
    body = results[0].json()
    assert all(result.json() == body for result in results)
    dataset_id = UUID(body["dataset"]["id"])
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(orm.Dataset).where(orm.Dataset.name == name)) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(orm.Transaction).where(orm.Transaction.dataset_id == dataset_id)
            )
            == 1
        )

    with TestClient(create_app(settings)) as restarted:
        assert upload(restarted, name, key=key).json() == body
        conflict = upload(restarted, name, key=key, boundary="source-a")
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IMPORT_IDEMPOTENCY_CONFLICT"

    another_scope = settings.model_copy(update={"demo_analyst": "second-local-source"})
    with TestClient(create_app(another_scope)) as scoped:
        assert upload(scoped, name, key=key).json()["dataset"]["id"] != str(dataset_id)


def test_invalid_csv_releases_key_and_explicit_keys_allow_intentional_copies(client):
    name, key = str(uuid4()), str(uuid4())
    assert upload(client, name, content=b"invalid\n", key=key).status_code == 422
    accepted = upload(client, name, key=key)
    assert accepted.status_code == 201
    distinct = upload(client, name, key=str(uuid4()))
    assert distinct.status_code == 201
    assert accepted.json()["dataset"]["id"] != distinct.json()["dataset"]["id"]


def test_database_rejects_transaction_linked_to_another_datasets_batch(client, factory):
    left = upload(client, str(uuid4())).json()
    right = upload(client, str(uuid4())).json()
    left_id, right_batch = UUID(left["dataset"]["id"]), UUID(right["batch_id"])
    with pytest.raises(IntegrityError, match="fk_transactions_batch_dataset"), session_scope(factory) as session:
        session.execute(
            update(orm.Transaction).where(orm.Transaction.dataset_id == left_id).values(import_batch_id=right_batch)
        )
    with session_scope(factory) as session:
        assert session.scalar(
            select(orm.Transaction.import_batch_id).where(orm.Transaction.dataset_id == left_id)
        ) == UUID(left["batch_id"])
