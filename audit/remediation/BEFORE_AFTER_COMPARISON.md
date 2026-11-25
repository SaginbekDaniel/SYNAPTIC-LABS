# Сравнение с исходным аудитом

Веса, 10-балльная техническая шкала и нормировка взяты из исходного аудита. Баллы отражают локальную экспертную оценку стенда по evidence, без претензии на официальный результат жюри ITU HACKATHON-2026.

| Категория | Вес | Было | Стало | Вклад | Подтверждение и причины удержанных баллов |
|---|---:|---:|---:|---:|---|
| Core functionality | 15% | 8 | 9 | 13,5 | CSV, точные числа, PostgreSQL replay и case проверены. Нет банковского контура. |
| Fraud detection accuracy | 15% | 4 | 5 | 7,5 | Holdout V3 показывает снижение FP при том же recall. Синтетика и недостаточная precision. |
| Fraud prevention | 10% | 3 | 5 | 5,0 | Выполняется sandbox intervention с ack. Нет платежного подключения. |
| Customer protection | 10% | 4 | 6 | 6,0 | Устойчивые предупреждения, повтор и SCA simulation. Реальная SCA отсутствует. |
| Security | 10% | 4 | 6 | 6,0 | Локальный RBAC/tenant, dependency audit, runtime SQL scopes. Нет живого IdP и внешнего security review. |
| Architecture and code quality | 10% | 7 | 8 | 8,0 | Версионируемые inputs, durable queues, миграции и контракты. Источники банка отсутствуют. |
| Reliability | 5% | 6 | 8 | 4,0 | Корректный readiness, crash cap и restart recovery. Нет HA/DR. |
| Performance and scalability | 5% | 6 | 8 | 4,0 | Быстрый импорт, меньше SQL. Лимиты графа и замедление P95 depth 2 на 100k. |
| Testing quality | 5% | 8 | 9 | 4,5 | 255/255, новый failure coverage и независимые прогоны. Нет долгого cloud нагрузочного теста и UI coverage. |
| Frontend and UX | 5% | 8 | 9 | 4,5 | Async CSV и durable transfer в браузере. Нет проверки отдельным аудитом accessibility. |
| Innovation | 5% | — | — | — | Достаточного конкурентного сравнения нет. |
| Deployment and demo readiness | 5% | 6 | 7 | 3,5 | Native Nginx, preflight, статический Railway. Cloud/image runtime недоступны. |
| **Итого с оценёнными категориями** | **95%** | **53,0/100** | — | **66,5/100** | **Нормировка 55,8 → 70,0/100 при 95% веса.** |

## Четыре задачи кейса BCC

| Цель | Было | Стало | Основание |
|---|---:|---:|---|
| A. Предотвращение | 3 | 5 | Point-in-time preflight, intervention и ack в sandbox |
| B. Защита клиента | 4 | 6 | Customer message, step-up, durable replay и recovery |
| C. Подозрительные операции | 4 | 5 | Сравнимый V3 ablation, временные доказательства, риск FP сохраняется |
| D. Банковская безопасность | 7 | 8 | Actor, tenant roles, audit, источник и версия решения |
| **Среднее** | **4,5/10** | **6,0/10** | Локальная готовность к показу |

Технический прототип пригоден для локальной демонстрации после запуска release preflight. Для банковского пилота нужен полученный от банка разрешённый sandbox и shadow validation. Production требует OIDC/SSO, банковского канала, SCA/ack, HA/DR, operational readiness и внешней проверки.

Исходный независимый стресс — 58,82% precision, 50,00% recall, 63,64% FPR, значения V2 сохранились. V3 на новом synthetic-протоколе сравнивается со старым алгоритмом на точных тех же входах — 13,89 → 33,71% precision, recall 83,33 → 83,33%, FPR 73,81 → 23,41%. Эти две строки разных наборов напрямую не сравниваются. Transfer holdout в прежнем протоколе остался 85,29% / 64,44% / 7,46%. Синхронный импорт 100 000 строк ускорился примерно с 59,08 до 1,75 с. Readiness теперь различает reachable/missing/outdated, и hard-stop тест не превышает три попытки. Аудит frontend lockfile прошёл с нулём известных advisories в измерении.

[Исходная оценка](../HACKATHON_READINESS.md) · [Тесты](FINAL_TEST_REPORT.md) · [Fraud](FRAUD_ENGINE_V3_REPORT.md) · [Performance](PERFORMANCE_IMPROVEMENTS.md) · [Security](SECURITY_REMEDIATION_REPORT.md)
