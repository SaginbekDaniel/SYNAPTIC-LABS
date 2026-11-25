# Local setup

## Текущий стенд ремедиации

Для новых сценариев нужен PostgreSQL, обновлённый через Alembic до 0007. Для фронтенд toolchain используйте Node 22.12+ в ветке 22 или поддерживаемую ветку Node 24. В [локальном сценарии](../../audit/remediation/HACKATHON_DEMO_GUIDE.md) приведены команды подготовки отдельной синтетической БД, временные роли customer/reviewer и release preflight. Интеграционные тесты требуют выделенные disposable БД и управляют их схемами.

Two ways to run NEXORA locally. Both use synthetic data only.

## A. Production-like stack (Docker Compose) — quickest

Requires Docker with Compose v2.

```bash
docker compose up --build -d --wait
```

Open http://127.0.0.1:8080 → **Лаборатория** (Fraud Lab) → *Сгенерировать набор* → *Запустить анализ*
→ *Перейти к алертам*.

* Same topology as the cloud: gateway (`web`) → `api` → `postgres`, plus `worker`; migrations run
  once in the `migrate` service before the API starts.
* Every port binds to `127.0.0.1`. Gateway access control is **off** by default for this reason.
  To try it, set `NEXORA_GATEWAY_AUTH=basic`, `NEXORA_GATEWAY_USER` and a ≥ 16-character
  `NEXORA_GATEWAY_PASSWORD` in `.env` (copy `.env.example`) and restart `web`.
* API docs: http://127.0.0.1:8000/docs. Direct API calls need the header
  `X-Nexora-Gateway-Token: local-gateway-token` (the compose default).
* Stop with `docker compose down` (data kept) or `docker compose down -v` (data dropped).

## B. Development servers (hot reload)

Requires Python 3.12 or 3.13 with [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16.

Create the role and databases once (adjust to your PostgreSQL setup):

```bash
psql -U postgres -c "CREATE ROLE nexora LOGIN PASSWORD 'nexora' CREATEDB"
```

```bash
for db in nexora nexora_test nexora_e2e; do createdb -U postgres -O nexora "$db"; done
```

Install and migrate:

```bash
make setup
```

```bash
make migrate
```

Run in three terminals:

```bash
make api
```

```bash
make worker
```

```bash
make web
```

The UI is at http://127.0.0.1:5173 and proxies `/api` to port 8000. Settings come from
environment variables or `.env` (see `.env.example`); defaults match the commands above.

## Common problems

| Problem | Fix |
|---|---|
| `/health/ready` → 503, `migration: null` | Run `make migrate`. |
| Jobs stay `queued` | The worker is not running (`make worker`). |
| Integration tests are skipped | PostgreSQL not reachable at `NEXORA_TEST_DATABASE_URL`. |
| `web` container exits with `refusing to start` | Gateway auth is `basic` without valid credentials; see section A. |
| Port 5432 in use (compose) | Compose maps PostgreSQL to `127.0.0.1:5433`. |
