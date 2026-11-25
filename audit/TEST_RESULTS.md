# Результаты тестов

25 ноября 2026 года · `feat/transfer-protection` · commit `43368ff46b788568d34ceee5ac8ae9135728c373`. Все штатные suites выполнены локально на изолированных данных. Шаги запуска и конфигурация приведены в [руководстве](TEST_EXECUTION_GUIDE.md). Числа ниже относятся к окончательным прогонам, предварительные попытки перечислены отдельно.

| Suite / проверка | Всего | Прошло | Не прошло | Skipped | Время | След |
|---|---:|---:|---:|---:|---:|---|
| Штатный pytest, PostgreSQL 16.16 | 150 | 150 | 0 | 0 | 3,76 с | [Лог](evidence/pytest-postgres.log) · [JUnit](evidence/pytest-postgres.xml) |
| Штатный pytest, lock + coverage | 150 | 150 | 0 | 0 | 7,47 с | [Лог](evidence/pytest-locked.log) · [JUnit](evidence/pytest-locked.xml) |
| Vitest, 4 файловых suite | 26 | 26 | 0 | 0 | 0,20 с | [Лог](evidence/vitest.log) |
| Playwright E2E desktop / mobile | 14 | 14 | 0 | 0 | 27,8 с | [Лог](evidence/playwright-e2e.log) · [JSON](evidence/playwright-e2e.json) |
| Playwright smoke, native Nginx / production bundle | 5 | 5 | 0 | 0 | 10,1 с | [Лог](evidence/playwright-smoke.log) · [JSON](evidence/playwright-smoke.json) |
| Новые pytest audit checks | 31 | 28 | 3 | 0 | 0,85 с | [Лог](evidence/pytest-audit.log) · [JUnit](evidence/pytest-audit.xml) |
| Новые browser audit checks | 2 | 2 | 0 | 0 | 2,0 с | [Лог](evidence/playwright-audit.log) · [JSON](evidence/playwright-audit.json) |
| Lifecycle diagnostics | 7 сценариев | 5 ожидаемых | 2 отклонения | 0 | 9,21 с wall | [Лог](evidence/lifecycle.log) · [JSON](evidence/lifecycle.json) |
| Controlled fraud scenarios | 31 | 14 классификаций | 17 отклонений | 0 | см. per scenario | [Лог](evidence/independent-fraud.log) · [JSON](evidence/independent-fraud.json) |

Результат 150 не суммируется с повторным запуском. Всего 195 уникальных штатных автоматизированных проверок прошло и 33 новых автоматизированных проверок дали 30 pass и 3 обнаруженных дефекта. Lifecycle и классификационные эксперименты идут отдельно. Штатный Python suite имеет 107 tests в `tests/unit` и 43 в `tests/integration`, включая проверки transfer без БД. Точные suite/file results доступны в JUnit. Coverage для штатного pytest — 3 878 / 4 171 statements (92,98%) и 722 / 880 branches (82,05%). Combined 91,07%. Frontend coverage не измерялся. Статическая типизация TypeScript прошла в production build. [Coverage per file](evidence/coverage-python.txt) · [Coverage JSON](evidence/coverage-python.json)

### Что проверялось и какие assertions дают доверие

- Штатный Python suite подсчитывает повторы по source ID, проверяет схему ответов, границы money, tie/day order, temporal conservation, частичное покрытие, stale version, prior commits и DB audit. Хороший пример — `tests/integration/test_api.py:38–50`, где заявленная сумма пересчитывается по исходным transfers. `test_graph_limits_are_clamped` проверяет число nodes и caps, но не стоимость SQL.
- В `test_persistence.py` реально используется PostgreSQL. Инъекция сбоя worker в unit/integration упражняет обработку исключений и лизинг, физический многократный crash появился в новом lifecycle. `test_transfer_checks.py` проверяет payload, ограничение данных и политики отказа, но preset profile и токен задаются fixture.
- Vitest преимущественно проверяет formatting, i18n, helper logic и evaluation view model. Реальные React страницы покрываются Playwright. Отдельного component coverage и полного автоматизированного WCAG audit нет.
- E2E использует реальные API, worker и PostgreSQL. Штатный UI-journey проверяет case reload и причины. Smoke seed зависит от текущего времени, что затрудняет точный replay. Общий collector console ошибок чувствителен к окружению (пример со fonts ниже). Ошибки/задержки routing mocking в новых тестах симулируют отказ браузерного соединения, повторный запрос идёт к настоящему локальному API.
- Новая Python suite добавила негативные UUID/required fields/types, empty CSV, малый upload cap, корреляцию ошибок и trace ID, 6 concurrent submits, csv → DB → worker → evidence → case decision, сохранность trace и stable evidence. Штатный job test и новый параллельный кейс дополняют друг друга.
- Новый Playwright flow проверяет отказ сети, отсутствие кнопки успешного завершения при `UNAVAILABLE`, повтор и равенство DOM state ответу API. Второй проверяет labels, keyboard submit, `aria-invalid`, `role=alert` и `aria-live`. Проверены desktop Chromium и штатный mobile viewport 390 px. Firefox, WebKit, реальные устройства и screen reader не вошли.
- OpenAPI содержит 29 method/path operations. /docs, /redoc и /openapi.json дали 200/404 при включении/выключении. Сгенерированная схема совпала с tracked JSON без записи. [Список routes](evidence/api-contract.log)

### Отклонения в новых тестах

| Проверка | Ожидалось | Фактически | Причина и повтор |
|---|---|---|---|
| `test_same_csv_submission_is_idempotent` | Тот же идентификатор набора при повторе того же запроса | Два 201 и разные UUID | Endpoint создаёт новый dataset до scoped dedup. `pytest audit/tests -k same_csv`. |
| `test_csv_rejects_duplicate_headers` | Отклонение неоднозначных amount columns | Парсер принял, одно значение потеряно | Header uniqueness не проверяется. `pytest audit/tests -k duplicate_headers`. |
| `test_http_method_error_keeps_allow_header` | 405 с Allow GET | 405, заголовок отсутствует | Общий exception handler не передаёт заголовки Starlette. `pytest audit/tests -k allow_header`. |
| `outdated_migration` | readiness 503 на 0001 | HTTP 200 | Проверяется наличие номера. Повтор diagnostic lifecycle на чистой БД. |
| `worker_hard_stop_three_times` | terminal failed в рамках лимита 3 после трёх crash | succeeded, attempt_count 4 | SQL claim не ограничивает expired lease. Повтор diagnostic lifecycle со своим pgdata. |

Пять остальных lifecycle checks подтвердили readiness без схемы и после head, PostgreSQL CHECK/FK с rollback, outage 503 и persistence после рестартов. На пустой, но живой БД HTTP 503 ожидаем, флаг database=false является отдельной диагностической проблемой D06. [Raw lifecycle](evidence/lifecycle.json)

17 отклонений fraud включают 10 misses и 7 false alerts. Это отдельные измерения качества продукта на размеченных сценариях. Один штатный повторный warning — StarletteDeprecationWarning adapter HTTPX. [Fraud report](FRAUD_DETECTION_REPORT.md)

### Окружение, статические проверки и попытки с блокерами

| Команда или запуск | Что наблюдалось | Причина и следующий шаг |
|---|---|---|
| `uv sync --frozen --python …` и чистый `npm ci` | Python dependencies установлены за 105,24 с wall, npm web 9,43 с, IaC дополнительно менее 1 с | Изолированная копия. Сборка на Python 3.13.18 и Node 24.22.0/macOS. Документация и CI ориентированы на Node 22. [uv](evidence/uv-clean.log) · [npm](evidence/npm-clean.log) |
| `ruff check`, `ruff format --check`, `mypy` | 77 Python файлов отформатированы, mypy 56 source files без ошибок | Проверка штатных каталогов. [Ruff/mypy](evidence/python-static.log) |
| `alembic check` | No new upgrade operations detected | Схема head совпала с моделями SQLAlchemy. [Лог](evidence/alembic-check.log) |
| `npm run build`, `npm run check` для Railway | Production SPA build работает, IaC checker подтверждает 3 сервиса и DB | TS/Vite build 2,35 с wall. [Build](evidence/web-build.log) · [IaC](evidence/railway-clean.log) |
| `docker compose -p nexora-audit config --quiet` | Exit 0 | Compose resolution/validation прошли. [Config](evidence/compose-config.log) |
| `docker compose -p nexora-audit up --build -d --wait` | Не стартовало. Клиент не смог открыть Unix socket Docker daemon | Host availability, Docker Compose v5.7.0. Использованы native Postgres/uvicorn/worker/Vite и адаптированный Nginx. [Лог Docker](evidence/docker.log) · [PG](evidence/postgres-setup.log) |
| Preflight pytest при недоступной БД | 128 passed, 22 skipped, 2,05 с | DB-зависимые проверки из первого прогона повторены на своей БД, все 150 прошли. [Лог](evidence/pytest-no-db.log) |
| Playwright до установки Chromium | 14 ошибок открытия browser | Требовался headless shell pinned revision 1243. [Лог](evidence/playwright-e2e-bootstrap.log) · [Установка](evidence/playwright-install.log) |
| Playwright с временной symlink раскладкой node_modules | 8 pass, 6 fail с font HTTP 403 | Vite serving allowlist для файлов за пределами apps/web. Обычное расположение node_modules дало 14 pass без правки продукта. [Лог](evidence/playwright-e2e-symlink.log) |
| `npm audit` при сетевом ограничении | Registry ENOTFOUND | Повтор к публичному advisory registry дал содержательный отчёт. [Лог](evidence/npm-audit.log) · [Security](SECURITY_REPORT.md) |
| Live Railway, Docker image runtime, edge TLS, production privileges | Blocked / unverified в рамках этого аудита | Docker daemon не работал, live smoke пишет данные, изолированный Railway sandbox не предоставлен. Использовалось локальное приближение без работы с чужими сервисами. |
| Полная банковская валидация / платёжный workflow | Blocked / отсутствует реализация | Использованы синтетические наборы и IBM toy sample. Настоящие платежи, private data и credentials не использовались. |
