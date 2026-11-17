#!/usr/bin/env bash
# Start a disposable API + worker against a freshly migrated database for browser E2E tests.
# Usage: NEXORA_DATABASE_URL=... scripts/e2e_stack.sh <port>
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8100}"
: "${NEXORA_DATABASE_URL:?NEXORA_DATABASE_URL must point at a disposable database}"
uv run alembic downgrade base >/dev/null
uv run alembic upgrade head >/dev/null
uv run python -m nexora.worker.runner &
WORKER=$!
trap 'kill "$WORKER" 2>/dev/null || true' EXIT INT TERM
uv run uvicorn nexora.api.main:app --host 127.0.0.1 --port "$PORT"
