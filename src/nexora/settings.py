"""Runtime settings from environment variables (never from committed secrets)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXORA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://nexora:nexora@localhost:5432/nexora"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    demo_analyst: str = "demo-analyst"  # DEMO MODE identity — not production authentication
    max_upload_bytes: int = 20 * 1024 * 1024
    max_csv_rows: int = 200_000
    graph_max_depth: int = 3
    graph_max_nodes: int = 300
    graph_max_edges: int = 1500
    job_lease_seconds: int = 120
    job_max_attempts: int = 3
    worker_poll_seconds: float = 1.0
    # Recorded benchmark artifacts served read-only to the Evaluation screen.
    benchmark_results_dir: str = str(Path(__file__).resolve().parents[2] / "benchmarks" / "results")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
