# Реализация по этапам

Стартовый HEAD 43368ff46b788568d34ceee5ac8ae9135728c373. Ветка feat/nexora-audit-remediation. [Развёрнутый реестр файлов, тестов и ограничений по каждому из 33 пунктов](ISSUE_RESOLUTION_REGISTER.csv).

| Этап | Изменения и критерий | Проверка |
|---|---|---|
| Подготовка | Сверены commit, ветки, неизменённый исходный аудит и .DS_Store. Воспроизведены PostgreSQL, Vite, Playwright и Nginx. | 195/195 штатных, 28/31 исходных audit pytest до изменений. |
| Целостность и runtime | D01–D06, D20. Новая миграция с composite FK, обработка CSV, безопасные headers, release heads и bounded retry. | 159 Python и 31/31 исходных audit pytest в первой фазе. Physical hard stops и restart отдельно. |
| Fraud | D07/D08/D17 и F01/F03/F04. Optional V3, trusted context, persisted pinning, новые split и ablation. | Stable benchmarks совпали, синтетический V3 протокол и holdout записаны. Bank holdout открыт. |
| Transfer | D14/D16 и F02. Generic scoped intent, append-only actions, безопасный API/UI, миграция 0004. | Повтор, app recreation, refusal и step-up даны в PostgreSQL integration и browser. |
| Security | S01–S08. IdentityVerifier, tenant scoping, профили, доработанные ошибки, DB roles, front-end security pins. | Tenant tests, DB grants preflight и advisory scans. OIDC, Docker/Railway и independent sink требуют внешних ресурсов. |
| Performance | D09/D10/D11/D12. Durable COPY, batched queries, индексированный flow. | 100k HTTP и async, P95+SQL counts, dense и million. D11 остаётся в continuation. |
| UX и analyst | D13/F05. CSV upload, state, расследование, reviewed labels. | Browser CSV → case, tenant-scoped independent correction и export. |
| Deployment и handoff | D15/D18/D19. IaC, reproducible preflight, контракты и документация. | Nginx native smoke, npm check, OpenAPI/types parity. Рабочая ветка не опубликована. |

[Итог](IMPLEMENTATION_SUMMARY.md) · [Финальный прогон](FINAL_TEST_REPORT.md) · [Оставшееся](REMAINING_LIMITATIONS.md)
