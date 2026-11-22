"""A request_id quoted from an error envelope leads to the log line that explains it (H-03, backlog B-015)."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from nexora.logging_config import JsonFormatter

pytestmark = pytest.mark.integration


@pytest.fixture()
def app_and_logs(settings) -> Iterator[tuple[FastAPI, io.StringIO]]:
    from nexora.api.main import create_app

    app = create_app(settings)

    # Probe routes outside /api (the authentication dependency only guards /api; nothing here is mounted in
    # production code). They fail the way real handlers can.
    def boom() -> None:
        raise RuntimeError('unexpected "quoted" failure\nwith a second line')

    def db_down() -> None:
        raise OperationalError("SELECT 1", {}, Exception('connection to "db" refused'))

    def chatty() -> dict[str, str]:
        logging.getLogger("nexora.api").info("work inside a request")
        return {"ok": "yes"}

    app.add_api_route("/probe/boom", boom)
    app.add_api_route("/probe/db-down", db_down)
    app.add_api_route("/probe/chatty", chatty)

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("nexora.api")
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield app, stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


def _entries(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.mark.parametrize(
    ("path", "status", "code", "level"),
    [("/probe/boom", 500, "INTERNAL_ERROR", "ERROR"), ("/probe/db-down", 503, "DATABASE_UNAVAILABLE", "ERROR")],
)
def test_error_envelope_request_id_is_in_the_log_line(app_and_logs, path, status, code, level) -> None:
    app, stream = app_and_logs
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get(path)
    assert r.status_code == status and r.json()["error"]["code"] == code
    rid = r.json()["error"]["request_id"]
    assert rid and rid == r.headers.get("X-Request-ID", rid)
    matching = [e for e in _entries(stream) if e.get("request_id") == rid]
    assert matching, stream.getvalue()
    assert matching[0]["level"] == level
    if status == 500:
        assert 'RuntimeError: unexpected "quoted" failure\nwith a second line' in matching[0]["exc"]


def test_a_client_supplied_request_id_is_echoed_and_logged(app_and_logs) -> None:
    app, stream = app_and_logs
    with TestClient(app) as client:
        r = client.get("/probe/chatty", headers={"X-Request-ID": "support-ticket-4711"})
        other = client.get("/probe/chatty")
    assert r.headers["X-Request-ID"] == "support-ticket-4711"
    entries = [e for e in _entries(stream) if e["msg"] == "work inside a request"]
    assert [e.get("request_id") for e in entries] == ["support-ticket-4711", other.headers["X-Request-ID"]]
