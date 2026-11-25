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


JOB_FAILURE_MESSAGES = {
    "ANALYSIS_FAILED": "analysis failed",
    "ATTEMPTS_EXHAUSTED": "analysis retry budget exhausted",
    "DATASET_NOT_FOUND": "analysis dataset is unavailable",
    "ANALYSIS_CONFIG_INVALID": "stored analysis configuration is invalid",
    "SNAPSHOT_IDENTITY_CONFLICT": "analysis snapshot could not be published",
}


def public_job_error(code: str | None) -> tuple[str | None, str | None]:
    if code is None:
        return None, None
    public_code = code if code in JOB_FAILURE_MESSAGES else "ANALYSIS_FAILED"
    return public_code, JOB_FAILURE_MESSAGES[public_code]
