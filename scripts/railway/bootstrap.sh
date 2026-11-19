#!/usr/bin/env bash
# One-time setup of the NEXORA demo on Railway (docs/deployment/railway.md).
#
# Requires: Railway CLI >= 5.63 signed in (`railway login`, or RAILWAY_API_TOKEN for an account /
# workspace token), an active Railway plan, Node 22, openssl and uv (to hash the first password).
#
#   scripts/railway/bootstrap.sh
#
# Creates (or reuses) the project, applies .railway/railway.ts (PostgreSQL, api, worker, web),
# sets the secrets over stdin, deploys the checked-out commit and generates the public domain.
# Safe to re-run: existing secrets are kept and nothing is deleted.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PROJECT="${NEXORA_RAILWAY_PROJECT:-nexora-ai-demo}"
CREDENTIALS="${NEXORA_CREDENTIALS_FILE:-$HOME/.config/nexora/railway-demo.env}"

railway whoami >/dev/null
if ! railway status --json >/dev/null 2>&1; then
  echo "==> creating Railway project $PROJECT"
  railway init --name "$PROJECT" ${NEXORA_RAILWAY_WORKSPACE:+--workspace "$NEXORA_RAILWAY_WORKSPACE"}
fi

echo "==> validating and applying .railway/railway.ts"
(cd .railway && npm ci --no-audit --no-fund && npm run check)
railway config plan
# Without --confirm-destructive the CLI refuses to delete anything non-interactively.
railway config apply --yes

has_variable() { # <service> <name>
  railway variable list --service "$1" --json | python3 -c 'import json,sys; sys.exit(0 if sys.argv[1] in json.load(sys.stdin) else 1)' "$2"
}
set_secret() { # <service> <name> <value>  — value travels over stdin, never argv
  printf '%s' "$3" | railway variable set "$2" --stdin --service "$1" --skip-deploys >/dev/null
}

echo "==> secrets"
umask 077
mkdir -p "$(dirname "$CREDENTIALS")"
if [ ! -f "$CREDENTIALS" ]; then
  # Legacy shared Basic credential: only used if the gateway is switched back to NEXORA_GATEWAY_AUTH=basic.
  password="$(openssl rand -base64 33 | tr -d '/+=\n')"
  printf 'NEXORA_GATEWAY_USER=analyst\nNEXORA_GATEWAY_PASSWORD=%s\n' "$password" > "$CREDENTIALS"
  unset password
fi
if ! grep -q '^NEXORA_ANALYST_USER=' "$CREDENTIALS"; then
  # First named analyst for the sign-in page. Only its Argon2id hash leaves this machine.
  printf 'NEXORA_ANALYST_USER=analyst.one\nNEXORA_ANALYST_PASSWORD=%s\n' "$(openssl rand -base64 24 | tr -d '/+=\n')" >> "$CREDENTIALS"
fi
# shellcheck disable=SC1090
. "$CREDENTIALS"
if ! has_variable api NEXORA_GATEWAY_TOKEN; then
  set_secret api NEXORA_GATEWAY_TOKEN "$(openssl rand -hex 32)"
fi
set_secret web NEXORA_GATEWAY_USER "$NEXORA_GATEWAY_USER"
set_secret web NEXORA_GATEWAY_PASSWORD "$NEXORA_GATEWAY_PASSWORD"
if ! has_variable api NEXORA_BOOTSTRAP_PASSWORD_HASH; then
  # The API creates this account at start-up if it does not exist (nexora.auth.service.bootstrap_from_settings).
  hash="$(printf '%s\n' "$NEXORA_ANALYST_PASSWORD" | uv run --quiet python -m nexora.auth.cli hash-password --password-stdin)"
  set_secret api NEXORA_BOOTSTRAP_USERNAME "$NEXORA_ANALYST_USER"
  set_secret api NEXORA_BOOTSTRAP_PASSWORD_HASH "$hash"
  unset hash
fi
echo "    credentials: $CREDENTIALS (keep it private; share through a password manager)"

scripts/railway/deploy.sh

echo "==> public HTTPS domain (gateway only)"
railway domain --service web --json
