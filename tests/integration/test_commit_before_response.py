"""Read-your-writes: a write is committed before its response reaches the client.

FastAPI runs the code after ``yield`` in a request-scoped dependency *after* the response
has been sent. With the commit there, a client that immediately follows up (the Lab
creates a dataset and at once requests its analysis) can observe ``DATASET_NOT_FOUND``;
this happened on the slower CI runner (audit F-14). The test drives the ASGI app directly
and checks, from an independent connection, that the row is visible at the instant the
response starts.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import create_engine, text

from nexora.api.main import create_app

pytestmark = pytest.mark.integration


def test_created_dataset_is_committed_before_the_response_starts(settings, db_url):
    app = create_app(settings)
    engine = create_engine(db_url)
    body = json.dumps({"suite": "funnel-only-v1", "seed": 4242}).encode()
    seen: dict[str, object] = {}
    chunks: list[bytes] = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]
            with engine.connect() as c:  # independent connection: sees committed rows only
                seen["visible_rows"] = c.execute(text("SELECT count(*) FROM datasets")).scalar_one()
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    with engine.connect() as c:
        before = c.execute(text("SELECT count(*) FROM datasets")).scalar_one()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/lab/datasets",
        "raw_path": b"/api/v1/lab/datasets",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json"), (b"host", b"test")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    asyncio.run(app(scope, receive, send))
    assert seen["status"] == 201, b"".join(chunks)
    assert seen["visible_rows"] == before + 1
