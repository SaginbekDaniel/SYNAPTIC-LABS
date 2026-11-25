# Итоговая проверка

Среда — 25 ноября 2026, macOS 27.0.1 arm64, Apple M4, Python 3.13.18, Node 24.22.0, PostgreSQL 16.16, headless Chromium, native Nginx 1.28.0. Все тестовые данные синтетические или публичный тестовый образец. Runtime запускался на loopback в отдельных временных БД. Платёжных операций не было.

| Набор | До | Итог | Доказательство |
|---|---:|---:|---|
| Штатный Python и новые регрессии | 150/150 | 175/175 | [JUnit](evidence/final-pytest.xml) |
| Исходные audit pytest | 28/31 | 31/31 | [До](evidence/baseline-audit.log) · [После](evidence/final-pytest.log) |
| Vitest | 26/26 | 26/26 | [Лог](evidence/final-vitest.log) |
| Playwright продукт | 14/14 | 16/16 | [JSON](evidence/final-browser.json) |
| Playwright исходного аудита | 2 сценария | 2/2 | [Журнал](evidence/final-browser.log) |
| Native Nginx deployed smoke | 5/5 | 5/5 | [Лог](evidence/final-smoke/run.log) |
| Сумма по строкам с тестами | — | 255/255 | Без повторного счёта pytest и без диагностики lifecycle |
| HTTP release preflight | — | passed | [JSON](evidence/release-preflight.json) |
| Раздельные DB-права | — | девять отказов и разрешённый агрегат | [SQL-state](evidence/db-privilege-boundaries.json) |

Покрытие считается по исходным файлам nexora с branch measurement. Итог — 93,91% statements и 84,19% branches. Точные числа сохранены в [машиночитаемом отчёте](evidence/final-coverage.json). База сравнения 92,98% statements и 82,05% branches. Из исходных тестов обновлена миграционная изоляция для проверки downgrade с сохранением formations и oracle. Добавлены тесты BOM и нормализации, параллельного и scoped CSV replay, композитного FK, readiness, pinning политики, устойчивости задачи импорта, авторизации, независимого рецензирования, временного контекста, границ flow и sandbox. Тест отказа worker дополнен синтетическим секретом в новом и историческом error summary. Новые browser tests проводят CSV → case и sandbox warning → reload → reviewer → ack. Все 195 исходных штатных проверок сохранены.

Первый объединённый Python запуск использовал неверную роль локального PostgreSQL и дал 4 failures и 40 skipped. Повтор с правильной ролью дал ноль failures/skips. Первый запуск staged Nginx smoke пропустил benchmark artifact и дал 404 для desktop и mobile. Повтор с тем же опубликованным fixture дал 5/5. В логах остаются предупреждения Starlette/httpx и Cytoscape. Проверка, что подстановка API типов идентична версии в репозитории, проходит в статическом наборе.

## Команды воспроизведения

В отдельном checkout с установленными pinned зависимостями укажите свои disposable DSN для NEXORA_TEST_DATABASE_URL, NEXORA_AUDIT_DATABASE_URL, NEXORA_E2E_DATABASE_URL и миграций. Интеграционные и Playwright проверки сбрасывают disposable схемы. Покрытие и тестовый вывод пишите в отдельный каталог.

```bash
uv sync --frozen --all-groups
npm --prefix apps/web ci
uv run alembic upgrade head
uv run --with coverage==7.13.5 coverage run --branch --source=nexora -m pytest -o addopts='' -q tests audit/tests
uv run --with coverage==7.13.5 coverage report
uv run alembic check
uv run ruff check src tests migrations scripts/release_preflight.py audit/remediation/tools
uv run mypy src
npm --prefix apps/web test
npm --prefix apps/web run build
npm --prefix apps/web exec -- playwright install chromium
npm --prefix apps/web run test:e2e
uv run python scripts/export_openapi.py /tmp/nexora-openapi.json
cmp apps/web/openapi.json /tmp/nexora-openapi.json
(cd apps/web && npx --no-install openapi-typescript /tmp/nexora-openapi.json -o /tmp/nexora-api-types.ts)
cmp apps/web/src/lib/api-types.ts /tmp/nexora-api-types.ts
npm --prefix .railway run check
npm --prefix apps/web audit --json
npm --prefix apps/web audit --omit=dev --json
uv run python scripts/run_benchmark.py --out /tmp/nexora-bench.json --report /tmp/nexora-bench.md
uv run python scripts/run_transfer_protection_evaluation.py --output /tmp/nexora-transfer-eval.json
uv run python audit/remediation/tools/context_evaluation.py /tmp/nexora-context-eval.json
git diff --check
```

Исходный browser audit можно выполнить в временной копии spec из audit/tests/transfer-browser.spec.ts в apps/web/e2e. Deployed smoke выполняется через playwright.smoke.config.ts на native Nginx по исходной [инструкции](../TEST_EXECUTION_GUIDE.md). [Worker hard stop и restart](evidence/phase1-lifecycle.json) проведены физической остановкой процессов в отдельном временном PostgreSQL на этапе 0003 и [повторены на финальной схеме 0007](evidence/final-lifecycle/results.json). Для диагностического сценария используется [тот же отдельный инструмент](tools/lifecycle_regression.py), который разрешает остановку только audit-owned cluster и temporary DSN. [Release preflight](HACKATHON_DEMO_GUIDE.md) и [процедура анализа производительности](PERFORMANCE_IMPROVEMENTS.md) воспроизводятся отдельно.

Docker runtime и image security verification заблокированы недоступным daemon. Live Railway, внешняя OIDC, bank sandbox и численное покрытие JS не проверялись. Эти проверки не входят в количество pass. [Docker](evidence/compose-final.log) · [IaC](evidence/railway-check.log) · [Статика](evidence/final-static.log)
