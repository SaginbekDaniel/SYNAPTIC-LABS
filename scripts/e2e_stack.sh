#!/usr/bin/env bash
# Start a disposable API + worker against a freshly migrated database for browser E2E tests.
# Usage: NEXORA_DATABASE_URL=... scripts/e2e_stack.sh <port>
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8100}"
: "${NEXORA_DATABASE_URL:?NEXORA_DATABASE_URL must point at a disposable database}"
uv run python scripts/reset_disposable_db.py >/dev/null
# Disposable analysts for the browser tests, created through the operator CLI (password via stdin).
: "${NEXORA_E2E_PASSWORD:?NEXORA_E2E_PASSWORD must be set (test-only password for the disposable database)}"
for user in e2e.analyst e2e.second; do
  printf '%s\n' "$NEXORA_E2E_PASSWORD" | uv run python -m nexora.auth.cli create-user "$user" --display-name "E2E ${user#e2e.}" --password-stdin >/dev/null
done
uv run python -m nexora.worker.runner &
WORKER=$!
trap 'kill "$WORKER" 2>/dev/null || true' EXIT INT TERM
uv run uvicorn nexora.api.main:app --host 127.0.0.1 --port "$PORT"
