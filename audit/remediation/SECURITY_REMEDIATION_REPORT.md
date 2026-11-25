# Security после ремедиации

| Область | Реализация и проверка | Граница |
|---|---|---|
| Principal и RBAC | IdentityVerifier, валидация claims, аналитик, reviewer, administrator, customer, service. Customer/ref, tenant filters и deny-by-default на защищённых путях. Cross-tenant list/detail и смена статуса проверены. | OIDC/SSO issuer, revocation и production ingress требуют интеграции. Shared demo доступен в локальных профилях. |
| Application profiles | Development поддерживает loopback. Deployed demo требует gateway secret и закрытую документацию. Production требует внешний verifier и выключает demo endpoints. | Nginx Basic для публичной демонстрации очищает входной Authorization. Индивидуальная работа проверена напрямую на защищённом loopback, реальный authentication gateway требует отдельной настройки. |
| Ошибки | Stable error codes, public summary и request ID. В регрессии синтетический URL с credentials отсутствует в ответе и логах, включая старый сохранённый summary. Пропускаются Allow, WWW-Authenticate, Retry-After. | Политика экспортируемых логов и централизованная корреляция требуют операционных процедур. |
| DB | Миграции от owner, отдельные API и worker runtime groups, отдельный audit appender и read-only агрегат для reporting. Локальные тесты дали девять 42501 и разрешили неперсональный агрегат. Full preflight прошёл под раздельными ролями. | Cloud роли провайдера и продвижение SQL grants на реальный managed PostgreSQL не проверены. Tenant scope обеспечивается в API. |
| Audit | Case audit и sandbox actions append-only. Case feedback пишет независимого рецензента и evidence digest. Sandbox отделяет immutable evidence и mutable status, а acknowledgement содержит actor и action ID. | Владелец БД остаётся доверенной стороной. Независимый sink, период хранения и внешняя сверка целостности отсутствуют. |

## Воспроизводимость supply chain

Прямые pins frontend: react-router-dom 7.18.7, Vite 8.3.8, @vitejs/plugin-react 6.3.0, Vitest 5.1.2. Advisory counts по полному lockfile 8 → 0, runtime-only 2 → 0. Сохранены исходные и итоговые JSON, Vitest, TypeScript build и Playwright прошли. pip-audit проверил pinned Python runtime из установленного окружения, известных advisories на момент прогона не найдено. Frontend CycloneDX SBOM сгенерирован. Образный SBOM, digest pinning контейнеров и container scanning требуют работающего Docker runtime и воспроизводимого release commit. Native Nginx smoke подтверждает CSP и gateway в локальной сборке.

Для проверки ролей на выделенной базе запустите Alembic от schema owner, затем примените scripts/postgres_runtime_roles.sql через psql с ON_ERROR_STOP. Миграционная роль owner не используется процессами приложения. Провайдер должен выдать API/worker отдельные LOGIN principals без elevated grants и назначить каждому свою NOLOGIN group. Передайте каждому процессу свой NEXORA_DATABASE_URL. Reporting получает доступ только к nexora_operational_totals, а audit appender наследуется от API. Локальный тест переключал права через SET ROLE на временном PostgreSQL и выполнил полный release preflight.

Railway IaC объявляет ссылки на управляемые секреты. Минимум 32 символа для gateway и analyst token, значения задаются в secret store. Базовый deployment не находится в scope этой реализации.

[Права](evidence/db-privilege-boundaries.json) · [Preflight с раздельными ролями](evidence/db-roles-preflight.json) · [npm runtime](evidence/npm-audit-runtime-after.json) · [npm все](evidence/npm-audit-after.json) · [pip-audit](evidence/python-audit.json) · [SBOM](evidence/frontend-sbom.cdx.json) · [SQL](../../scripts/postgres_runtime_roles.sql)
