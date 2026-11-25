# Воспроизведение аудита

Исходное состояние — `feat/transfer-protection`, `43368ff46b788568d34ceee5ac8ae9135728c373`. Для точной репликации используйте отдельный checkout и БД только для synthetic audit. Штатные integration и E2E сбрасывают **схему целевой тестовой БД**. Имена с suffix `_test` или `_e2e` являются защитой в тестовом helper, проверяйте ещё host и порт. Не подставляйте существующую development, cloud или customer database.

## Изолированный checkout и PostgreSQL

Из корня репозитория, в Bash или Zsh. Версии на host — Python 3.13.18, uv 0.13.9, Node 24.22.0, npm 11.19.1, PostgreSQL 16.16, Playwright 1.63.0. README устанавливает Node 22. У Docker образа своя версия. Потребуются `git`, `uv`, Python 3.12–3.13, Node/npm и доступ к публичным registries.

```bash
repo="$(pwd -P)"
scratch="$(mktemp -d /tmp/nexora-audit.XXXXXX)"
git clone --local --no-hardlinks --branch feat/transfer-protection "$repo" "$scratch/repo"
cd "$scratch/repo"
test "$(git rev-parse HEAD)" = 43368ff46b788568d34ceee5ac8ae9135728c373
mkdir -p audit/tests
cp "$repo"/audit/tests/* audit/tests/
out="$scratch/evidence"
mkdir -p "$out"
export UV_CACHE_DIR="$scratch/uv-cache"
export UV_PROJECT_ENVIRONMENT="$PWD/locked-venv"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/browsers"
uv sync --frozen
uv pip install --python "$UV_PROJECT_ENVIRONMENT/bin/python" coverage==7.13.5 pip-audit==2.10.0 bandit==1.9.4
(cd apps/web && npm ci && npx playwright install chromium)
(cd .railway && npm ci && npm run check)
export UV_NO_SYNC=1
```

При доступном Docker можно использовать отдельный контейнер PostgreSQL. Название контейнера должно быть свободным. Режим подключения trust рассчитан на одноразовый loopback стенд.

```bash
docker run --rm -d --name nexora-audit-postgres -e POSTGRES_USER=auditor \
  -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:49571:5432 postgres:16-alpine
docker exec nexora-audit-postgres pg_isready -U auditor
for db in nexora_audit_test nexora_audit_e2e nexora_audit_perf nexora_audit_smoke nexora_audit_migrate; do
  docker exec nexora-audit-postgres createdb -U auditor "$db"
done
```

В аудите Docker daemon не работал. Native PostgreSQL 16.16 arm64 был распакован из `@embedded-postgres/darwin-arm64@16.16.0-beta.19` во временную папку. Для точного повтора lifecycle поместите корень чистого checkout непосредственно в `mktemp -d /tmp/nexora-audit.XXXXXX`, например через `git archive HEAD | tar -xf - -C "$scratch"`, затем скопируйте audit tests и выполните install команды из этого каталога. Native кластер должен быть отдельным и доступным только на loopback. При отсутствии standalone client `createdb` используйте Python.

```bash
mkdir -p "$scratch/tools"
(cd "$scratch/tools" && npm pack @embedded-postgres/darwin-arm64@16.16.0-beta.19 --silent
 mkdir -p postgres
 tar -xzf embedded-postgres-darwin-arm64-16.16.0-beta.19.tgz -C postgres)
pgbin="$scratch/tools/postgres/package/native/bin"
mkdir -p "$scratch/pgsocket"
"$pgbin/initdb" --auth=trust --username=auditor --no-locale --encoding=UTF8 -D "$scratch/pgdata"
"$pgbin/pg_ctl" -D "$scratch/pgdata" -l "$scratch/postgres.log" -w \
  -o "-h 127.0.0.1 -p 49571 -k $scratch/pgsocket" start
uv run python - <<'PY'
import psycopg
from psycopg import sql
names = ("nexora_audit_test", "nexora_audit_e2e", "nexora_audit_perf",
         "nexora_audit_smoke", "nexora_audit_migrate")
with psycopg.connect("postgresql://auditor@127.0.0.1:49571/postgres", autocommit=True) as conn:
    for name in names:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
PY
```

## Штатные и новые тесты

```bash
export NEXORA_TEST_DATABASE_URL=postgresql+psycopg://auditor@127.0.0.1:49571/nexora_audit_test
export NEXORA_AUDIT_DATABASE_URL="$NEXORA_TEST_DATABASE_URL"
export NEXORA_E2E_DATABASE_URL=postgresql+psycopg://auditor@127.0.0.1:49571/nexora_audit_e2e
uv run ruff check src tests migrations
uv run ruff format --check src tests migrations
uv run mypy
uv run coverage run --branch --source=nexora -m pytest -o addopts='' -q -ra \
  --junitxml "$out/pytest-locked.xml" > "$out/pytest-locked.log" 2>&1
uv run coverage report -m > "$out/coverage-python.txt"
uv run coverage json -o "$out/coverage-python.json"
uv run pytest -o addopts='' -q --tb=short -ra audit/tests \
  --junitxml "$out/pytest-audit.xml" > "$out/pytest-audit.log" 2>&1
```

Вызов audit pytest ожидаемо возвращает exit 1 на проверенной ревизии из-за D01, D02 и D05. В штатном pytest ожидается 150 pass. При запуске audit pytest отдельно от штатного заранее накатите Alembic head в одноразовую test DB. Перед browser suite убедитесь, что локальные 8100 и 5180 свободны, browser binaries установлены и нормальный реальный `apps/web/node_modules` лежит внутри checkout.

```bash
(cd apps/web && npm test && npm run build)
(cd apps/web && PLAYWRIGHT_JSON_OUTPUT_FILE="$out/playwright-e2e.json" \
  npx --no-install playwright test --reporter=list,json) > "$out/playwright-e2e.log" 2>&1

cp audit/tests/transfer-browser.spec.ts apps/web/e2e/audit-transfer-browser.spec.ts
(cd apps/web && PLAYWRIGHT_JSON_OUTPUT_FILE="$out/playwright-audit.json" \
  npx --no-install playwright test audit-transfer-browser.spec.ts --reporter=list,json) \
  > "$out/playwright-audit.log" 2>&1
```

Копия `audit-transfer-browser.spec.ts` существует только в тестовом checkout и добавляется после штатного прогона. Новый тест браузера не сохраняет customer state и не вызывает внешние сервисы.

## Deployment и smoke

Для проверки production-like Compose используйте отдельный project name и выделенные порты/том в тестовой среде.

```bash
docker compose -p nexora-audit config --quiet
docker compose -p nexora-audit up --build -d --wait
(cd apps/web && NEXORA_SMOKE_URL=http://127.0.0.1:8080 \
  PLAYWRIGHT_JSON_OUTPUT_FILE="$out/playwright-smoke.json" \
  npx --no-install playwright test -c playwright.smoke.config.ts --reporter=list,json)
```

В приведённой Compose команде локальная auth конфигурация берётся из собственного изолированного окружения. Чтобы повторить проверку Basic, настройте тестовую пару `NEXORA_GATEWAY_USER` / `NEXORA_GATEWAY_PASSWORD`, включите `NEXORA_GATEWAY_AUTH=basic` и передайте ту же пару через `NEXORA_SMOKE_USER` / `NEXORA_SMOKE_PASSWORD` без вывода значений. Native smoke, использованный в аудите, генерирует собственную случайную пару и доступен через script ниже. Он использует production bundle, repo template, loopback `18080`/ `18100`, локальные includes и тестовый htpasswd. Для native smoke требуется чистая `nexora_audit_smoke`, Python env в `locked-venv`, Chromium в `browsers`, и Nginx 1.28.0 на пути `tools/nginx-src/nginx-1.28.0/objs/nginx` (configure с `--with-http_realip_module` и доступным PCRE2). Аудит собрал Nginx из официального tarball с `--with-pcre=../pcre2-10.45` и `make -j4`.

```bash
(cd apps/web && npm run build)
bash audit/tests/run-native-smoke.sh "$out" > "$out/playwright-smoke.log" 2>&1
```

### Миграции, crash и DB restart

Запускайте только против native cluster из текущего временного каталога. `lifecycle_experiment.py` останавливает этот процесс PostgreSQL и только свои worker/API. Перед выполнением завершите другие тесты на этом экземпляре. Нужна пустая `nexora_audit_migrate`.

```bash
uv run python audit/tests/lifecycle_experiment.py "$out/lifecycle.json" \
  --scratch "$scratch" --pg-ctl "$pgbin/pg_ctl" \
  --dsn postgresql://auditor@127.0.0.1:49571/nexora_audit_migrate \
  > "$out/lifecycle.log" 2>&1
```

Ожидаемые отклонения исходного commit доступны в JSON. Для завершения native стенда остановите только созданный кластер через `"$pgbin/pg_ctl" -D "$scratch/pgdata" -m fast -w stop`. Выход lifecycle сам останавливает порождённые API/worker.

## Fraud benchmarks

Для точного свидетельства запускайте CLI в чистом Git checkout commit, сохраняя результаты за пределами tracked paths. Наличие untracked audit scripts может повлиять на provenance, классификации от этого не меняются. Проектные артефакты остаются исходными. Независимый сценарий и IBM sample используют те же pinned runtime зависимости.

```bash
uv run python scripts/run_benchmark.py --out "$out/bench-v1-rerun.json" --report "$out/bench-rendered.md"
uv run python scripts/run_transfer_protection_evaluation.py --output "$out/transfer-holdout-rerun.json"
uv run python audit/tests/compare_benchmarks.py . "$out" > "$out/benchmark-comparison.json"
uv run python audit/tests/fraud_experiment.py "$out/independent-fraud.json" > "$out/independent-fraud.log"
git clone https://github.com/IBM/AMLSim.git "$scratch/ibm-amlsim"
git -C "$scratch/ibm-amlsim" checkout 7338a4bcb1af9bcfea2201ad7daccfe2a4d569ca
uv run python audit/tests/external_amlsim.py \
  "$scratch/ibm-amlsim/sample/outputs" "$out/external-amlsim.json"
```

Сопоставляйте `benchmarks/results/bench-v1.json` и `benchmarks/transfer_protection/results/holdout-v1.json` с соответствующим rerun, исключив `generated_at`, `runtime_seconds`, `latency_ms`, `environment`, `code`, `git_commit` и `git_worktree_dirty`. Те же параметры и seed необходимы для прямого сравнения. [Результат](FRAUD_DETECTION_REPORT.md)

## Производительность

```bash
for n in 100 1000 10000 100000 1000000; do
  uv run python audit/tests/performance_experiment.py "$out/perf-core-$n.json" --size "$n"
done
uv run python audit/tests/performance_experiment.py "$out/perf-core-dense.json" --size 10000 --dense
uv run python audit/tests/performance_experiment.py "$out/perf-risk.json" --risk-timing
```

Проба миллиона создаёт до 1,9 GiB peak RSS на audit host. Для серии API используйте пустую `nexora_audit_perf` или свежую БД с тем же suffix. В двух отдельных терминалах запустите API и worker с теми же environment vars. Остановите их после выполнения.

```bash
export NEXORA_DATABASE_URL=postgresql+psycopg://auditor@127.0.0.1:49571/nexora_audit_perf
export NEXORA_WORKER_POLL_SECONDS=0.2
uv run alembic upgrade head
uv run alembic check
uv run uvicorn nexora.api.main:app --host 127.0.0.1 --port 18101 --no-access-log
# Отдельный терминал с теми же environment vars:
uv run python -m nexora.worker.runner
# Из третьего терминала:
uv run python audit/tests/performance_experiment.py "$out/perf-api.json" \
  --url http://127.0.0.1:18101 --dsn postgresql://auditor@127.0.0.1:49571/nexora_audit_perf
```

Для независимой реплики повторите со свежей `nexora_repeat_audit_perf`. При сборе RSS/CPU аудитор снимал `ps -p <audit PID> -o %cpu=,rss=` каждые примерно 250 мс для API и worker. SQL statement count измерялся через SQLAlchemy events в local TestClient на опубликованных snapshots.

```bash
uv run python audit/tests/query_counts.py "$out/query-counts.json" --dsn "$NEXORA_DATABASE_URL"
```

[Измерения](PERFORMANCE_REPORT.md)

## Dependency и статические проверки

```bash
uv export --frozen --format requirements-txt --no-dev --no-emit-project --no-hashes > "$out/python-runtime-pins.txt"
uv run pip-audit -r "$out/python-runtime-pins.txt" --no-deps --disable-pip -f json -o "$out/pip-audit.json"
(cd apps/web && npm audit --json) > "$out/npm-audit.json"
(cd apps/web && npm audit --omit=dev --json) > "$out/npm-audit-runtime.json"
(cd .railway && npm audit --json) > "$out/npm-audit-railway.json"
uv run bandit -q -r src/nexora scripts -f json -o "$out/bandit.json"
```

`npm audit` и Bandit могут возвращать ненулевой код при наличии записей. Сравнивайте severity, количество и область пакетов с датой выполнения. [Security results](SECURITY_REPORT.md)

## Артефакты

Полный список созданных файлов — [FILES_CREATED.txt](FILES_CREATED.txt). Основные машиночитаемые материалы лежат в `evidence/`. `pytest-*.xml` и `playwright-*.json` содержат идентификаторы и результаты тестов. `*-rerun.json`, `independent-fraud.json`, `external-amlsim.json`, `perf-*.json` и `lifecycle.json` подтверждают диагностику, классификации и замеры. `ISSUE_REGISTER.csv` содержит 33 пункта. Рабочая копия и штатные источники аудитом не изменены.
