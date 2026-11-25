"""FastAPI application factory."""

from __future__ import annotations

import hmac
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from nexora import __version__
from nexora.analytics.config import AnalysisConfig, default_config
from nexora.analytics.context import VerifiedContext
from nexora.api import schemas
from nexora.api.identity import IdentityVerifier, LocalTokenVerifier
from nexora.api.routes import alerts, analysis, cases, datasets, evaluation, sandbox, transfer_checks
from nexora.application.errors import AppError
from nexora.application.transfer_demo import PROFILE_PATH, TransferDemo, load_policy, load_profiles
from nexora.application.transfer_sandbox import BeneficiaryAdapter, FixtureBeneficiaryAdapter, SandboxPaymentAdapter
from nexora.persistence.db import session_factory
from nexora.persistence.health import database_readiness, release_heads
from nexora.settings import Settings, get_settings

log = logging.getLogger("nexora.api")

GATEWAY_TOKEN_HEADER = "X-Nexora-Gateway-Token"
# Paths reachable without the gateway token: liveness/readiness for the platform's health checks.
_UNGATED_PREFIXES = ("/health/",)


def _envelope(
    status: int, code: str, message: str, request_id: str | None, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id, "details": details or {}}},
        headers={"X-Request-ID": request_id or ""},
    )


def create_app(
    settings: Settings | None = None,
    config: AnalysisConfig | None = None,
    *,
    identity_verifier: IdentityVerifier | None = None,
    beneficiary_adapter: BeneficiaryAdapter | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="NEXORA AI API",
        version=__version__,
        description=(
            "Explainable, coverage-aware fraud-network investigation. DEMO MODE: synthetic data, no bank integration."
        ),
        docs_url="/docs" if settings.expose_api_docs else None,
        redoc_url="/redoc" if settings.expose_api_docs else None,
        openapi_url="/openapi.json" if settings.expose_api_docs else None,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory(settings.database_url)
    app.state.analysis_config = config or default_config()
    try:
        app.state.verified_context_catalog = (
            TypeAdapter(dict[str, VerifiedContext]).validate_json(Path(settings.verified_context_catalog).read_bytes())
            if settings.verified_context_catalog
            else {}
        )
    except (OSError, ValueError):
        raise ValueError("verified context catalog is invalid or unavailable") from None
    provisioned = settings.local_identity_provisioning.get_secret_value()
    if settings.execution_profile != "development":
        if len(settings.gateway_token) < 32 or settings.expose_api_docs or "*" in settings.cors_origins:
            raise ValueError("deployed API requires gateway authentication, private docs and explicit origins")
        if settings.execution_profile == "deployed_demo" and (
            settings.transfer_protection_enabled and len(settings.transfer_analyst_token.get_secret_value()) < 32
        ):
            raise ValueError("deployed transfer demo requires analyst evidence provisioning")
    if settings.execution_profile == "production" and (
        identity_verifier is None or provisioned or isinstance(identity_verifier, LocalTokenVerifier)
    ):
        raise ValueError("production requires an external identity verifier")
    app.state.authenticated_analytics = settings.authenticated_analytics or settings.execution_profile == "production"
    app.state.identity_verifier = identity_verifier or (
        LocalTokenVerifier.from_json(provisioned) if provisioned else None
    )

    if app.state.authenticated_analytics and app.state.identity_verifier is None:
        raise ValueError("authenticated analytics requires an identity verifier")
    try:
        transfer_policy = load_policy()
    except (OSError, ValueError):
        log.error("Transfer protection policy configuration is unavailable or invalid")
        transfer_policy = None
    app.state.transfer_demo = TransferDemo(
        transfer_policy,
        load_profiles(PROFILE_PATH) if settings.transfer_protection_enabled else None,
        settings.transfer_protection_enabled,
        app.state.analysis_config.config_sha256,
    )

    demo = app.state.transfer_demo
    app.state.beneficiary_adapter = beneficiary_adapter or FixtureBeneficiaryAdapter.from_profiles(
        (demo.profiles or {}).values(),
        graph_config_sha256=demo.graph_config_sha256,
        available=demo.enabled and demo.profiles is not None,
    )
    app.state.payment_adapter = SandboxPaymentAdapter()

    gateway_token = settings.gateway_token

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
            "X-Nexora-Transfer-Analyst-Token",
        ],
        expose_headers=["X-Request-ID", "Location"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if 0 < len(incoming) <= 64 and incoming.isprintable() else f"req-{uuid.uuid4().hex[:16]}"
        request.state.request_id = rid
        if gateway_token and not request.url.path.startswith(_UNGATED_PREFIXES):
            presented = request.headers.get(GATEWAY_TOKEN_HEADER, "")
            if not hmac.compare_digest(presented.encode(), gateway_token.encode()):
                return _envelope(401, "GATEWAY_TOKEN_REQUIRED", "request did not arrive through the gateway", rid)
        if settings.execution_profile == "production" and request.url.path.startswith(
            ("/api/v1/demo/", "/api/v1/sandbox/")
        ):
            return _envelope(404, "NOT_FOUND", "demo endpoints are unavailable in production", rid)
        try:
            response = await call_next(request)
        except Exception:
            log.error("unhandled request failure; request_id=%s", rid)
            return _envelope(500, "INTERNAL_ERROR", "unexpected internal error", rid)
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(
            exc.status_code, exc.code, exc.message, getattr(request.state, "request_id", None), exc.details
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return _envelope(
            422,
            "REQUEST_INVALID",
            "request validation failed",
            getattr(request.state, "request_id", None),
            {"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = (
            "NOT_FOUND"
            if exc.status_code == 404
            else ("METHOD_NOT_ALLOWED" if exc.status_code == 405 else "HTTP_ERROR")
        )
        response = _envelope(exc.status_code, code, str(exc.detail), getattr(request.state, "request_id", None))
        safe_headers = {405: {"allow"}, 401: {"www-authenticate"}, 429: {"retry-after"}, 503: {"retry-after"}}
        for name, value in (exc.headers or {}).items():
            if name.lower() in safe_headers.get(exc.status_code, set()):
                response.headers[name] = value
        return response

    @app.exception_handler(OperationalError)
    async def db_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
        log.error("database unavailable; request_id=%s", getattr(request.state, "request_id", None))
        return _envelope(
            503,
            "DATABASE_UNAVAILABLE",
            "database is unavailable; retry later",
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled request failure; request_id=%s", getattr(request.state, "request_id", None))
        return _envelope(500, "INTERNAL_ERROR", "unexpected internal error", getattr(request.state, "request_id", None))

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    expected_migrations = release_heads()

    @app.get("/health/ready", response_model=schemas.Health, tags=["health"])
    def ready() -> Any:
        checks = database_readiness(app.state.session_factory, expected_migrations)
        healthy = checks["schema"] == "compatible"
        if settings.execution_profile == "production":
            checks["queue"] = {}
        body = {
            "status": "ok" if healthy else "degraded",
            "demo_mode": settings.execution_profile != "production",
            "actor": settings.demo_analyst if settings.execution_profile == "development" else "service",
            **checks,
        }
        return JSONResponse(status_code=200 if healthy else 503, content=body)

    for module in (datasets, analysis, alerts, cases, evaluation, transfer_checks, sandbox):
        app.include_router(module.router)
    return app


app = create_app()
