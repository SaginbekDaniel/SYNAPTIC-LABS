#!/usr/bin/env bash
set -eu
audit_out="$1"
native="$PWD/gateway"
nginx="$PWD/tools/nginx-src/nginx-1.28.0/objs/nginx"
mkdir -p "$native"
chmod 700 "$native"
export NEXORA_GATEWAY_TOKEN="$(openssl rand -hex 32)"
export NEXORA_SMOKE_USER=nexora_audit
export NEXORA_SMOKE_PASSWORD="$(openssl rand -hex 16)"
export NEXORA_SMOKE_URL=http://127.0.0.1:18080
export NEXORA_DATABASE_URL=postgresql+psycopg://auditor@127.0.0.1:49571/nexora_audit_smoke
export PLAYWRIGHT_BROWSERS_PATH="$PWD/browsers" PLAYWRIGHT_JSON_OUTPUT_FILE="$audit_out/playwright-smoke.json"
export NEXORA_EXPOSE_API_DOCS=false
node apps/web/docker/csp.mjs apps/web/dist/index.html > "$native/security-headers.conf"
printf '%s:' "$NEXORA_SMOKE_USER" > "$native/htpasswd"
printf '%s\n' "$NEXORA_SMOKE_PASSWORD" | openssl passwd -apr1 -stdin >> "$native/htpasswd"
chmod 600 "$native/htpasswd"
printf 'auth_basic "NEXORA demo";\nauth_basic_user_file %s/htpasswd;\n' "$native" > "$native/auth.conf"
: > "$native/listen-ipv6.conf"
python3 - "$native" <<'PY'
import os
import sys
from pathlib import Path
directory = Path(sys.argv[1])
replacements = {
    "${NGINX_LOCAL_RESOLVERS}": "127.0.0.1",
    "${NEXORA_API_UPSTREAM}": "127.0.0.1:18100",
    "${NEXORA_GATEWAY_TOKEN}": os.environ["NEXORA_GATEWAY_TOKEN"],
    "listen 8080;": "listen 127.0.0.1:18080;",
    "/tmp/nexora/": f"{directory}/",
    "/etc/nginx/nexora/": f"{directory}/",
    "/usr/share/nginx/html": str(Path("apps/web/dist").resolve()),
}
conf = Path("apps/web/docker/default.conf.template").read_text()
for old, new in replacements.items():
    conf = conf.replace(old, new)
(directory / "site.conf").write_text(conf)
(directory / "nginx.conf").write_text(
    "worker_processes 1;\nerror_log stderr warn;\npid nginx.pid;\n"
    "events { worker_connections 256; }\n"
    "http { include mime.types; access_log off; include site.conf; }\n"
)
PY
cp tools/nginx-src/nginx-1.28.0/conf/mime.types "$native/"
"$nginx" -p "$native/" -c nginx.conf -t
locked-venv/bin/alembic upgrade head
locked-venv/bin/python -m nexora.worker.runner > "$audit_out/smoke-worker.log" 2>&1 &
worker=$!
locked-venv/bin/uvicorn nexora.api.main:app --host 127.0.0.1 --port 18100 > "$audit_out/smoke-api.log" 2>&1 &
api=$!
"$nginx" -p "$native/" -c nginx.conf -g 'daemon off;' > "$audit_out/smoke-gateway.log" 2>&1 &
gateway=$!
trap 'kill "$gateway" "$api" "$worker" 2>/dev/null || true; wait || true' EXIT
for i in {1..80}; do
    curl -fsS http://127.0.0.1:18100/health/ready >/dev/null 2>&1 && break
    sleep 0.25
done
curl -fsS http://127.0.0.1:18100/health/ready
curl -fsS http://127.0.0.1:18080/healthz
cd apps/web
for i in {1..180}; do
    compgen -G "$PLAYWRIGHT_BROWSERS_PATH/chromium_headless_shell-*/INSTALLATION_COMPLETE" >/dev/null && break
    sleep 1
done
/usr/bin/time -p npx --no-install playwright test -c playwright.smoke.config.ts --reporter=list,json
