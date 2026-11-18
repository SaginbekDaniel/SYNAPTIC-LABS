"""FastAPI application factory."""

from __future__ import annotations

import hmac
import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from nexora import __version__
from nexora.analytics.config import AnalysisConfig, default_config
from nexora.api import schemas
from nexora.api.routes import alerts, analysis, cases, datasets, evaluation
from nexora.application.errors import AppError
from nexora.persistence import orm
from nexora.persistence.db import session_factory
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


def create_app(settings: Settings | None = None, config: AnalysisConfig | None = None) -> FastAPI:
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

    gateway_token = settings.gateway_token

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
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
        response = await call_next(request)
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
        return _envelope(exc.status_code, code, str(exc.detail), getattr(request.state, "request_id", None))

    @app.exception_handler(OperationalError)
    async def db_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
        log.error("database unavailable: %s", exc)
        return _envelope(
            503,
            "DATABASE_UNAVAILABLE",
            "database is unavailable; retry later",
            getattr(request.state, "request_id", None),
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return _envelope(500, "INTERNAL_ERROR", "unexpected internal error", getattr(request.state, "request_id", None))

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", response_model=schemas.Health, tags=["health"])
    def ready() -> Any:
        factory = app.state.session_factory
        try:
            with factory() as s:
                s.execute(text("SELECT 1"))
                migration = s.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
                queue = dict(
                    s.execute(select(orm.AnalysisJob.status, func.count()).group_by(orm.AnalysisJob.status)).all()
                )
            db_ok = True
        except Exception:
            db_ok, migration, queue = False, None, {}
        body = {
            "status": "ok" if db_ok and migration else "degraded",
            "database": db_ok,
            "migration": migration,
            "queue": {k: int(v) for k, v in queue.items()},
            "demo_mode": True,
            "actor": settings.demo_analyst,
        }
        return JSONResponse(status_code=200 if body["status"] == "ok" else 503, content=body)

    for module in (datasets, analysis, alerts, cases, evaluation):
        app.include_router(module.router)
    return app


app = create_app()
