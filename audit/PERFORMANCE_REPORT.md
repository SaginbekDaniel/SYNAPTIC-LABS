# Производительность и масштабирование

25 ноября 2026 года · `43368ff`. Apple M4, arm64, 10 CPU, 16 GiB RAM, macOS 27.0.1, Python 3.13.18, PostgreSQL 16.16, Node 24.22.0, headless Chromium 153.0.8010.12. Трафик loopback, отдельные БД, однопроцессный Uvicorn и один worker, poll 0,2 с. Измерены CSV parse/validation, pure pipeline, API + persistence, acknowledgement job, SQL count, read concurrency и небольшой browser navigation. Значения описывают этот host и synthetic workload. [Конфигурация хоста](evidence/hardware.log) · [Сценарий нагрузки](tests/performance_experiment.py)

## Pure pipeline

Основная форма нагрузки — повторяющиеся несложные пары, hub из 400 входных строк и редкие циклы. Пять повторов до 10 000 строк, два для 100 000 и dense, один для 1 000 000. Graph time входит в pipeline time. CPU и RSS замерены для всего процесса, включая создание synthetic input и Python import.

| Строки | Parse / validation, мс | Graph, мс | Pipeline, мс | Formations | Peak RSS, MiB | CPU% одного ядра |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 0,14 / 0,18 | 0,52 | 1,27 | 1 | 59,5 | ≈100 |
| 1 000 | 1,21 / 1,63 | 3,27 | 6,64 | 2 | 60,9 | ≈100 |
| 10 000 | 12,10 / 16,60 | 24,67 | 43,36 | 20 | 75,8 | ≈100 |
| 100 000 | 126,33 / 174,65 | 297,08 | 488,21 | 200 | 258,3 | ≈100 |
| 10 000 · cycles | 12,77 / 17,26 | 61,16 | 253,84 | 500, partial | 92,4 | ≈100 |
| 1 000 000 | ограничение CSV | 3 261,56 | 5 357,83 | 501, partial | 1 865,1 | ≈100 |

В плотной нагрузке 10 000 строк образуют 3 333 полных маленьких кольца до применения конфигурации. `cycle_budget_exceeded:KZT` ограничил выдачу до 500 formation. При миллионе Python API pipeline получил уже материализованный список. Generated CSV 61 118 256 байт превышает 20 MiB API body cap, отдельный вызов парсера дал `CSV_TOO_MANY_ROWS`. Миллион через HTTP и PostgreSQL не запускался. Throughput чистого анализа для 100 000 около 205 тыс. строк/с, для 1 000 000 около 187 тыс./с с неполной аналитикой. Dense случай в 5,85 раза медленнее основной выборки 10 000. Эти оценки не включают DB, API, queue и браузер. [Лог core](evidence/perf-core.log) · [Dense](evidence/perf-core-dense.json) · [Million](evidence/perf-core-1000000.json)

В отдельном замере вызовов risk scorer 100 000 строк создали 200 assessments. Правило затратило 1,43 мс суммарно, P50 0,0071 мс, P95 0,0078 мс, P99 0,0119 мс. Сбор evidence и temporal graph выполняются до scorer. [Фаза scoring](evidence/perf-risk.json)

## API, worker и БД

По одному холодному импорту каждого размера в двух отдельных базах, worker completion наблюдался с шагом 100 мс. Измерение completion включает polling/DB/worker publication. Latency read endpoints после warmup — 25 ответов на маршрут, P95 nearest rank, P99 в этой таблице не оценивался.

| Строки | Import два запуска, мс | Job enqueue, мс | До observed completion, мс | DB count execution, мс | Transactions P50/P95, мс |
|---:|---:|---:|---:|---:|---:|
| 100 | 29,35 / 25,10 | 7,19 | 216,68 | 0,03 | 2,02 / 3,13 |
| 1 000 | 151,32 / 154,68 | 2,29 | 215,95 | 0,09 | 2,11 / 2,75 |
| 10 000 | 1 754,87 / 1 751,92 | 2,38 | 318,27 | 0,79 | 3,33 / 4,30 |
| 100 000 | 59 081,47 / 58 391,76 | 12,86 | 2 137,21 | 4,44 | 27,44 / 28,54 |

| Строки | Neighborhood depth 1 P50/P95, мс | Depth 2 P50/P95, мс | Alerts P50/P95, мс | Overview P50/P95, мс |
|---:|---:|---:|---:|---:|
| 100 | 1,59 / 1,85 | 8,15 / 9,62 | 2,01 / 2,68 | 1,84 / 2,09 |
| 1 000 | 2,04 / 2,26 | 35,43 / 36,92 | 2,33 / 2,46 | 1,89 / 2,02 |
| 10 000 | 3,01 / 3,09 | 187,13 / 191,68 | 8,18 / 9,42 | 2,31 / 2,37 |
| 100 000 | 2,11 / 2,32 | 21,18 / 21,75 | 21,30 / 21,68 | 4,47 / 4,95 |

Повтор дал depth 2 P50 183,22 мс на 10 000 и 20,37 мс на 100 000. При чтении итоговой БД instrumentation видит 152 SQL statements для depth 2 на 150 nodes и 155 для 50 alerts. Это наблюдаемый N+1. Изменение latency по размеру нельзя приписать только объёму таблицы. Подробный per-node EXPLAIN и история статистики PostgreSQL отсутствуют. DB count в таблице — `SELECT count(*) WHERE dataset_id=…` с EXPLAIN ANALYZE, его время не равно latency всего endpoint. В повторном прогоне максимум по выборкам `ps` около 252 MiB RSS и 85,1% CPU для API, 428 MiB и 98,7% для worker. RSS PostgreSQL не измерялся. [Первый JSON](evidence/perf-api.json) · [Повтор](evidence/perf-api-repeat.json) · [SQL counts](evidence/query-counts.json) · [Process samples](evidence/perf-process-samples.tsv)

### Конкурентные чтения

По 120 запросов GET списка transactions (50 строк) на базе 100 000 строк для каждого уровня. HTTP status error rate 0% во всех четырёх уровнях. P99 описывает локальные измерения и при 120 samples зависит от нескольких запросов в хвосте. Инструмент использует одну shared HTTPX connection pool. Размер API DB pool ограничен.

| Одновременных клиентов | Запросов/с | P50, мс | P95, мс | P99, мс | Ошибки |
|---:|---:|---:|---:|---:|---:|
| 1 | 36,8 | 27,18 | 28,00 | 28,43 | 0/120 |
| 4 | 132,3 | 30,04 | 39,35 | 45,12 | 0/120 |
| 12 | 192,1 | 57,69 | 96,13 | 109,97 | 0/120 |
| 24 | 196,4 | 108,90 | 182,26 | 220,20 | 0/120 |

С 12 до 24 клиентов прибавка throughput около 2,3%, P95 почти удваивается. Штатному запуску импорта соответствует приблизительно 1 693 rows/s на 100 000 в первой пробе, включая транзакцию и ответ. Смешанная платёжная нагрузка и большое число concurrent uploads не измерялись.

## Browser и ограничения

Один dev Chromium navigation transfer screen дал DOMContentLoaded 41,5 мс, load 42,0 мс, first paint 44 мс, first contentful paint 72 мс. Это одиночная локальная точка с прогретым стендом. TransferSize 1549 байт относится к navigation resource. Production bundle Vite содержит main JS 277,42 kB (92,54 gzip), GraphCanvas/Cytoscape chunk 458,74 kB (147,04 gzip), CSS 72,71 kB (16,32 gzip). Граф браузерно функционален на smoke fixtures. Frame time на caps 300/1500 и slow-mobile Lighthouse не измерялись. [Browser log](evidence/playwright-audit.log) · [Build](evidence/web-build.log)

## Узкие места и проверяемые улучшения

1. Синхронный импорт 100 000 строк дважды занял 58–59 секунд на прямом API. Nginx proxy read timeout 60 секунд близок к этому времени. Python до DB тратит около 301 мс на parse/validation в pure benchmark. Следующий тест должен разделить inserts, SQL planning, indexes и WAL. API 202 на import jobs, staging/COPY и устойчивость к повторам проверять на 100 000–200 000 строк. [Endpoint](../src/nexora/api/routes/datasets.py#L32) · [DB path](../src/nexora/application/ingest_service.py#L95)
2. Neighborhood и alerts читают данные циклически. Установить лимит SQL на запрос и измерить batched queries/snapshot aggregates. [Queries](../src/nexora/application/queries.py#L488)
3. Max-flow строит пары соседних слоёв, peer проходы пересматривают cohort, cycle enumeration и chain ограничивают охват. Структурный стресс должен проверять partial stats вместе с latency. [Temporal](../src/nexora/analytics/temporal/flow.py#L110) · [Peer](../src/nexora/analytics/statistical/peer.py#L109)
4. До банковского SLA нужны нагрузка с реальной mix/prevalence, отдельные budgets на cold/warm, лонгран, concurrent writes, multi-worker, network RTT, failover и наблюдаемость. Локальные измерения не поддерживают оценку production capacity.
