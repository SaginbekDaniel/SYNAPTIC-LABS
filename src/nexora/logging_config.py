"""One JSON log line per record, for the API, the worker and uvicorn (H-03, backlog B-015).

Every line is produced by ``json.dumps``, so quotes, backslashes, newlines and tracebacks inside a message
can never break a log parser. Inside an API request the line carries the ``request_id`` that the error
envelope and the ``X-Request-ID`` header give to the user, so a quoted id leads to the log line.

The API process gets this configuration from uvicorn (``--log-config configs/logging.json``, which a test keeps
identical to :data:`LOGGING_CONFIG`); the worker calls :func:`configure_logging`.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import logging.config
from contextvars import ContextVar
from typing import Any

# Set by the API's request middleware. Each request runs in its own task, so the value never leaks between
# requests; outside a request it is None.
request_id_var: ContextVar[str | None] = ContextVar("nexora_request_id", default=None)

# Attributes every LogRecord has; anything else on a record came from ``extra=`` and is emitted as a field.
_STANDARD = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime", "taskName"}
_RESERVED = frozenset({"ts", "level", "logger", "msg", "request_id", "exc", "stack"})
# uvicorn attaches an ANSI-coloured duplicate of the message for terminals; it is noise in a log pipeline.
_DROPPED = frozenset({"color_message"})


class JsonFormatter(logging.Formatter):
    """``{"ts", "level", "logger", "msg", "request_id"?, "exc"?, "stack"?, ...extra}`` on one line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        for key, value in vars(record).items():
            if key not in _STANDARD and key not in _RESERVED and key not in _DROPPED and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exc"] = record.exc_text
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        # default=str: an unserialisable extra value degrades to its text instead of losing the line.
        return json.dumps(entry, ensure_ascii=False, default=str)


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "nexora.logging_config.JsonFormatter"}},
    "handlers": {"stderr": {"class": "logging.StreamHandler", "formatter": "json", "stream": "ext://sys.stderr"}},
    "root": {"level": "INFO", "handlers": ["stderr"]},
    # uvicorn's own loggers propagate to the root handler instead of using their plain-text handlers.
    "loggers": {
        "uvicorn": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
        "uvicorn.access": {"level": "INFO", "handlers": [], "propagate": True},
    },
}


def configure_logging() -> None:
    """Install the JSON configuration for this process (worker, CLI entry points)."""
    logging.config.dictConfig(LOGGING_CONFIG)
