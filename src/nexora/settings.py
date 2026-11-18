"""Runtime settings from environment variables (never from committed secrets)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The only SQLAlchemy dialect+driver NEXORA installs (psycopg 3). Hosted PostgreSQL providers
# (Railway, Heroku-style URLs) hand out ``postgres://`` or ``postgresql://`` URLs, which SQLAlchemy
# would map to the uninstalled psycopg2 driver.
_DRIVER_SCHEME = "postgresql+psycopg"
_PLAIN_SCHEMES = ("postgres", "postgresql")


def normalize_database_url(url: str) -> str:
    """Return ``url`` with a plain PostgreSQL scheme rewritten to the installed psycopg 3 driver.

    Only the scheme is touched; credentials, host, database and query parameters are preserved
    byte for byte. URLs that already name a driver (``postgresql+psycopg://``) or another database
    are returned unchanged so a misconfiguration fails loudly at connect time instead of silently.
    """
    stripped = url.strip()
    scheme, sep, rest = stripped.partition("://")
    if sep and scheme.lower() in _PLAIN_SCHEMES:
        return f"{_DRIVER_SCHEME}://{rest}"
    return stripped


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXORA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://nexora:nexora@localhost:5432/nexora"
    # Connection pool per process. The API and the worker each hold one pool; keep
    # (pool_size + max_overflow) x processes well under the database's max_connections.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Serve /docs, /redoc and /openapi.json. Disable in any internet-reachable deployment.
    expose_api_docs: bool = True
    # Shared secret the gateway (Nginx) attaches to every proxied request. When set, every /api route
    # rejects requests without it, so the API stays closed even if it is accidentally given a public
    # domain. Empty disables the check (local development, tests).
    gateway_token: str = ""
    # --- Authentication (server-side sessions; see nexora.auth) ---------------------------------
    # A session ends after this much inactivity, and in any case this long after sign-in.
    session_idle_minutes: int = Field(default=120, ge=5, le=24 * 60)
    session_absolute_hours: int = Field(default=12, ge=1, le=7 * 24)
    # Secure cookies need HTTPS (Railway's edge). Only the plain-HTTP local stack turns this off;
    # with it on the cookie also gets the __Host- prefix (no Domain, Path=/, Secure enforced by browsers).
    session_cookie_secure: bool = True
    # Extra origins allowed to send state-changing requests, comma separated (e.g. the public URL).
    # The request's own origin (Host + forwarded scheme) and the CORS origins are always trusted.
    trusted_origins: str = ""
    # Brute-force protection: failed sign-ins counted per user name and per client within a window.
    login_window_minutes: int = Field(default=15, ge=1, le=24 * 60)
    login_max_failures_per_user: int = Field(default=5, ge=1, le=1000)
    login_max_failures_per_client: int = Field(default=30, ge=1, le=10000)
    # One-time operator bootstrap (python -m nexora.auth.cli bootstrap): an Argon2id hash, never a password.
    bootstrap_username: str = ""
    bootstrap_password_hash: str = ""
    max_upload_bytes: int = 20 * 1024 * 1024
    max_csv_rows: int = 200_000
    graph_max_depth: int = 3
    graph_max_nodes: int = 300
    graph_max_edges: int = 1500
    job_lease_seconds: int = 120
    job_max_attempts: int = 3
    worker_poll_seconds: float = 1.0
    # Benchmark artifact written by scripts/run_benchmark.py; relative paths resolve from the repository root.
    benchmark_artifact: str = "benchmarks/results/bench-v1.json"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
