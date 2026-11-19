#!/usr/bin/env bash
# Deploy the checked-out commit to an existing NEXORA Railway project.
#
#   scripts/railway/deploy.sh            # uses the linked project/environment
#   RAILWAY_TOKEN=<project token> scripts/railway/deploy.sh   # CI (.github/workflows/deploy-railway.yml)
#
# Order: api first (its pre-deploy step applies migrations before it serves), then the worker,
# then the gateway. Each service must report SUCCESS before the next one starts.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain)" ] && [ "${NEXORA_ALLOW_DIRTY:-0}" != "1" ]; then
  echo "refusing to deploy: working tree has uncommitted changes (the deployment must be a commit)" >&2
  exit 1
fi
SHA="$(git rev-parse HEAD)"
ENV_ARGS=()
if [ -n "${RAILWAY_ENVIRONMENT_NAME:-}" ]; then ENV_ARGS=(--environment "$RAILWAY_ENVIRONMENT_NAME"); fi

latest_status() { # <service> -> status of the newest deployment ("UNKNOWN" if the API is unreachable)
  local json attempt
  for attempt in 1 2 3; do
    # Transient connection resets from the Railway API must not abort a half-finished rollout.
    if json="$(railway deployment list --service "$1" --limit 1 --json "${ENV_ARGS[@]}" 2>/dev/null)"; then break; fi
    json=""; sleep $((attempt * 3))
  done
  [ -n "$json" ] || { echo UNKNOWN; return 0; }
  printf '%s' "$json" | python3 -c '
import json, sys
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get("deployments", data.get("items", []))
print((items[0].get("status") if items else "NONE") or "UNKNOWN")'
}

wait_for_success() { # <service>
  local status deadline=$((SECONDS + ${NEXORA_DEPLOY_TIMEOUT:-900}))
  while (( SECONDS < deadline )); do
    status="$(latest_status "$1")"
    case "$status" in
      SUCCESS) echo "    $1: SUCCESS"; return 0 ;;
      FAILED|CRASHED|REMOVED|SKIPPED)
        echo "    $1: $status — recent logs:" >&2
        railway logs --service "$1" --lines 80 "${ENV_ARGS[@]}" >&2 || true
        return 1 ;;
      *) sleep 10 ;;
    esac
  done
  echo "    $1: timed out waiting for SUCCESS (last status: $status)" >&2
  return 1
}

deploy() { # <service> [path] [--path-as-root]
  local service="$1"; shift
  echo "==> $service @ ${SHA:0:12}"
  railway up "$@" --service "$service" "${ENV_ARGS[@]}" --ci --message "nexora ${SHA}"
  wait_for_success "$service"
}

deploy api
deploy worker
deploy web apps/web --path-as-root
echo "==> deployed ${SHA}"
