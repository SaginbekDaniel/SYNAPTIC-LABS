"""Application-level errors mapped to the HTTP error envelope by the API layer."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Invalid(AppError):
    status_code = 422


class PayloadTooLarge(AppError):
    status_code = 413


class Unauthorized(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class TooManyRequests(AppError):
    status_code = 429

    def __init__(self, code: str, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(code, message, {"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds
