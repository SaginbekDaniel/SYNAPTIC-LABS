"""Deployment hardening at the API boundary: gateway token and API documentation exposure."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nexora.api.main import GATEWAY_TOKEN_HEADER, create_app
from nexora.settings import Settings

TOKEN = "test-gateway-token-not-a-secret"


def _client(db_url: str, **overrides: object) -> TestClient:
    return TestClient(create_app(Settings(database_url=db_url, **overrides)))  # type: ignore[arg-type]


def test_api_rejects_requests_without_the_gateway_token(db_url: str) -> None:
    with _client(db_url, gateway_token=TOKEN) as c:
        for method, path in [("GET", "/api/v1/datasets"), ("POST", "/api/v1/datasets/generate")]:
            r = c.request(method, path, json={})
            assert r.status_code == 401, (method, path)
            assert r.json()["error"]["code"] == "GATEWAY_TOKEN_REQUIRED"
            assert r.headers["X-Request-ID"]
        wrong = c.get("/api/v1/datasets", headers={GATEWAY_TOKEN_HEADER: TOKEN + "x"})
        assert wrong.status_code == 401


def test_api_accepts_the_gateway_token(db_url: str) -> None:
    with _client(db_url, gateway_token=TOKEN) as c:
        r = c.get("/api/v1/datasets", headers={GATEWAY_TOKEN_HEADER: TOKEN})
        assert r.status_code == 200


def test_health_stays_reachable_for_platform_health_checks(db_url: str) -> None:
    with _client(db_url, gateway_token=TOKEN) as c:
        assert c.get("/health/live").status_code == 200
        assert c.get("/health/ready").status_code == 200


def test_docs_are_not_served_when_disabled(db_url: str) -> None:
    with _client(db_url, expose_api_docs=False) as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 404, path
    # The schema stays available in-process for the generated web client (scripts/export_openapi.py).
    assert "paths" in create_app(Settings(database_url=db_url, expose_api_docs=False)).openapi()


def test_docs_are_served_by_default_for_local_development(db_url: str) -> None:
    with _client(db_url) as c:
        assert c.get("/openapi.json").status_code == 200
