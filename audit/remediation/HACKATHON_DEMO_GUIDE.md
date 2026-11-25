# Локальная демонстрация для кейса BCC

Подготовьте пустую PostgreSQL 16 базу для synthetic rehearsal и передайте её DSN через NEXORA_DATABASE_URL. Запускайте команды из корня SYNAPTIC-LABS. Для Vite и Vitest нужна Node 22.12+ в ветке 22 или совместимая версия Node 24. Нужен Python 3.13 и uv. Для rehearsal команды ниже запускают три сервиса в фоне из одной конфигурации. Генерируйте значения локально и храните их в памяти терминала.

```bash
uv sync --frozen --all-groups
npm --prefix apps/web ci
npm --prefix apps/web run build
uv run alembic upgrade head

export NEXORA_VERIFIED_CONTEXT_CATALOG="$PWD/audit/remediation/fixtures/verified-context.json"
export NEXORA_PREFLIGHT_CUSTOMER="$(openssl rand -hex 32)"
export NEXORA_PREFLIGHT_REVIEWER="$(openssl rand -hex 32)"
export NEXORA_TRANSFER_ANALYST_TOKEN="$(openssl rand -hex 32)"
export NEXORA_GATEWAY_TOKEN="$(openssl rand -hex 32)"
export NEXORA_EXECUTION_PROFILE=deployed_demo
export NEXORA_EXPOSE_API_DOCS=false
export NEXORA_AUTHENTICATED_ANALYTICS=false
export NEXORA_TRANSFER_PROTECTION_ENABLED=true
export NEXORA_WORKER_POLL_SECONDS=0.2
export NEXORA_LOCAL_IDENTITY_PROVISIONING="$(uv run python - <<'PY'
import hashlib
import json
import os

def digest(variable):
    return hashlib.sha256(os.environ[variable].encode()).hexdigest()

print(json.dumps({
    digest("NEXORA_PREFLIGHT_CUSTOMER"): {
        "subject": "demo-customer", "tenant": "rehearsal", "role": "customer", "customer_ref": "demo-sender"
    },
    digest("NEXORA_PREFLIGHT_REVIEWER"): {
        "subject": "demo-reviewer", "tenant": "rehearsal", "role": "reviewer"
    },
}))
PY
)"
uv run uvicorn nexora.api.main:app --host 127.0.0.1 --port 8000 &
nexora_api_pid=$!
uv run python -m nexora.worker.runner &
nexora_worker_pid=$!
npm --prefix apps/web run preview -- --host 127.0.0.1 --port 4173 &
nexora_web_pid=$!
```

После запуска сервисов дождитесь HTTP 200 на /health/ready и на корне Vite preview. Подставьте заранее согласованный commit в аргументе preflight, для текущего локального worktree это стартовый 43368ff46b788568d34ceee5ac8ae9135728c373. Команда создаёт только synthetic fixtures в выбранной изолированной БД. JSON содержит фактическое подтверждение очереди, API, HTML, schema, transfer replay, отказа evidence без scope и результата sandbox действия.

```bash
uv run python scripts/release_preflight.py \
  --api http://127.0.0.1:8000 --web http://127.0.0.1:4173 \
  --expected-commit 43368ff46b788568d34ceee5ac8ae9135728c373
```

Для интерактивного loopback показа через Vite после preflight перезапустите только API. Оставьте worker и Vite preview. Вариант с development разрешён на изолированном адресе и сохраняет sandbox bearer authorization.

```bash
kill "$nexora_api_pid"
NEXORA_GATEWAY_TOKEN= NEXORA_EXECUTION_PROFILE=development \
  uv run uvicorn nexora.api.main:app --host 127.0.0.1 --port 8000 &
nexora_api_pid=$!
```

| Эпизод | Действия и наблюдение |
|---|---|
| 1. Подозрительная сеть | Fraud Lab → загрузить [suspicious-network.csv](fixtures/suspicious-network.csv) → дождаться 3 принятых строк → запустить «Экспериментальный контекст» → открыть alert, граф, temporal evidence, case → отметить начало расследования → audit. Preflight получил один alert и два case audit events. |
| 2. Легитимная похожая сеть | [verified-settlement.csv](fixtures/verified-settlement.csv) при том же профиле. Каталог связывает settlement refs с точным SHA-256 CSV. Preflight получил ноль alerts. Пояснить, что структурное совпадение осталось, а задокументированный расчёт ограничил score. Покажите reason code, cutoff, источник и band из [сохранённых риск-записей](evidence/demo-lookalike-evidence.json). Данные прочитаны из PostgreSQL по фактическим snapshot ID preflight. Для результата без alert стандартный список расследований эти детали не показывает. |
| 3. Защита перевода | Transfer Protection → Sandbox. Ввести customer token, demo-replay, 98 000 KZT, 2026-10-23T12:00:00Z. STEP_UP. Сохранить/открыть URL, взять reviewer token для evidence и проверки. Затем customer token и действие CONFIRM. Ожидаемый ack SIMULATED_COMPLETED. Повтор проверяется preflight с тем же action ID. |
| 4. Point in time | Новый intent на demo-replay, то же значение на 2026-10-20T12:00:00Z даёт ALLOW. Поздний cutoff даёт STEP_UP. После появления новой информации ранний assessment сохраняет первичную версию. |
| 5. Отказ источника | demo-timeout с поздней датой. Ожидается UNAVAILABLE и отказ действия, повторная оценка по ссылке на исходный assessment или отмена. Первичная запись остаётся в истории. |

Если readiness 503, сверьте database, schema и Alembic head. Если очередь долго accepted, проверьте имя БД worker и его локальный журнал. При 403 повторно проверьте scope и tenant, а в local developer profile — передачу sandbox bearer. Для резервного показа используйте сохранённые JSON и проверенную native сборку с [исходной инструкцией smoke](../TEST_EXECUTION_GUIDE.md). В smoke требуется опубликованный файл benchmarks/results/bench-v1.json. Docker или Railway для показа не обязательны. Данные, токены и симуляции создаются исключительно в выделенной демонстрационной среде.

[Успешный preflight](evidence/release-preflight.json) · [Браузерные сценарии](../../apps/web/e2e/remediation.spec.ts) · [Границы](REMAINING_LIMITATIONS.md)
