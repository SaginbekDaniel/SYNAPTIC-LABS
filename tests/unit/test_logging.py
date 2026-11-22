"""Structured logging: every line parses as JSON, whatever the message contains (H-03, backlog B-015)."""

from __future__ import annotations

import io
import json
import logging
import logging.config
from collections.abc import Iterator
from pathlib import Path

import pytest

from nexora.logging_config import LOGGING_CONFIG, JsonFormatter, request_id_var

ROOT = Path(__file__).resolve().parents[2]

HOSTILE = [
    'job failed: relation "transactions" does not exist',  # the line that broke the old worker format
    "back\\slash and a trailing backslash \\",
    "two\nlines\r\nand a tab\t",
    'already "json": {"msg": "x"}',
    "кириллица · emoji 🙂 · NUL \x00 · bell \x07",
    "%s %d %(name)s",  # printf directives without args must stay literal
]


@pytest.fixture()
def capture() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("nexora.test.logging")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        yield logger, stream
    finally:
        logger.removeHandler(handler)


def _lines(stream: io.StringIO) -> list[dict]:
    text = stream.getvalue()
    assert text.endswith("\n")
    return [json.loads(line) for line in text.splitlines()]  # one physical line per record


@pytest.mark.parametrize("message", HOSTILE)
def test_hostile_messages_stay_one_valid_json_line(capture, message: str) -> None:
    logger, stream = capture
    logger.error(message)
    [entry] = _lines(stream)
    assert entry["msg"] == message
    assert entry["level"] == "ERROR" and entry["logger"] == "nexora.test.logging"
    assert entry["ts"].endswith("+00:00") and "T" in entry["ts"]
    assert "request_id" not in entry  # outside a request


def test_the_old_worker_format_was_invalid_json() -> None:
    """Reproduces H-03 with the format string the worker used before this change."""
    old = logging.Formatter('{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    record = logging.LogRecord("nexora.worker", logging.ERROR, __file__, 1, HOSTILE[0], None, None)
    with pytest.raises(json.JSONDecodeError):
        json.loads(old.format(record))
    assert json.loads(JsonFormatter().format(record))["msg"] == HOSTILE[0]


def test_tracebacks_args_and_extra_fields_are_fields(capture) -> None:
    logger, stream = capture
    try:
        raise RuntimeError('boom "quoted"\nsecond line')
    except RuntimeError:
        logger.exception("job %s failed after %d attempts", "j-1", 3, extra={"job_id": "j-1", "attempts": 3})
    logger.info("with an object", extra={"thing": object()})
    first, second = _lines(stream)
    assert first["msg"] == "job j-1 failed after 3 attempts"
    assert first["job_id"] == "j-1" and first["attempts"] == 3
    assert first["exc"].startswith("Traceback") and 'RuntimeError: boom "quoted"\nsecond line' in first["exc"]
    assert second["thing"].startswith("<object object")  # unserialisable values degrade to text


def test_request_id_comes_from_the_context_or_the_record(capture) -> None:
    logger, stream = capture
    token = request_id_var.set("req-from-context")
    try:
        logger.info("inside a request")
        logger.info("explicit wins", extra={"request_id": "req-explicit"})
    finally:
        request_id_var.reset(token)
    logger.info("after the request")
    inside, explicit, after = _lines(stream)
    assert inside["request_id"] == "req-from-context"
    assert explicit["request_id"] == "req-explicit"
    assert "request_id" not in after


def test_uvicorn_log_config_file_is_the_python_configuration() -> None:
    """The API's uvicorn reads configs/logging.json; the worker uses LOGGING_CONFIG. They must not drift."""
    on_disk = json.loads((ROOT / "configs" / "logging.json").read_text(encoding="utf-8"))
    assert on_disk == LOGGING_CONFIG
    for path in ("Dockerfile", "scripts/e2e_stack.sh", "Makefile"):
        assert "--log-config configs/logging.json" in (ROOT / path).read_text(encoding="utf-8"), path


def test_dict_config_routes_uvicorn_loggers_through_the_json_handler() -> None:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    saved_uvicorn = {n: logging.getLogger(n).__dict__.copy() for n in ("uvicorn", "uvicorn.error", "uvicorn.access")}
    try:
        logging.config.dictConfig(LOGGING_CONFIG)
        stream = io.StringIO()
        [handler] = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
        handler.setStream(stream)  # type: ignore[attr-defined]
        logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:1", "GET", "/x", "1.1", 200)
        logging.getLogger("uvicorn.error").info("Started", extra={"color_message": "\x1b[36mStarted\x1b[0m"})
        logging.getLogger("nexora.api").warning('quote " inside')
        access, started, api = _lines(stream)
        assert started == {k: started[k] for k in ("ts", "level", "logger", "msg")}  # no ANSI duplicate
        assert access["logger"] == "uvicorn.access" and access["msg"] == '127.0.0.1:1 - "GET /x HTTP/1.1" 200'
        assert api["msg"] == 'quote " inside'
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])
        for name, state in saved_uvicorn.items():
            logging.getLogger(name).__dict__.update(state)
