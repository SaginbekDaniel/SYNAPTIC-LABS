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
