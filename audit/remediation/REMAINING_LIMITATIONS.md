# Оставшиеся ограничения

| Область | Текущее состояние | Что разблокирует следующую проверку |
|---|---|---|
| Банк и платёжная система | Sandbox проверен локально. Реальный hold, авторизация платежа, SCA и bank-side acknowledgement отсутствуют. | BCC sandbox, согласованный контракт идемпотентности и reconciliation, контроль доступа и наблюдаемость. |
| Качество fraud | V3 экспериментален. Независимый синтетический holdout не заменяет банковскую валидацию. | Разрешённые отложенные банковские наблюдения, независимо проверенные labels, review capacity и метрики customer harm. |
| Реальные сигналы | Источники подтверждённых adverse reports и settlement существуют в fixture. Device, takeover, возраст аккаунта и scam telemetry отсутствуют. | Доверенный point-in-time adapter, data contract и проверка provenance. |
| Analyst feedback | Reviewer API записывает независимое решение и экспортирует псевдоним одной активной метки. Массовая выгрузка и банковский calibration release ещё не проверены. | Управляемый bulk export, политика идентификаторов и изолированная калибровка на одобренных датасетах. |
| Валюты | Конфиг допускает разные пороги по currency, сохраняет exact money. Многовалютная калибровка и FX provenance не выполнены. | Исторические когорты, статистика и доверенные timestamped rates при необходимости. |
| Плотные графы | Есть budget и явный partial. Cycle budget 500, temporal limit 600 на один flow candidate. V3 публикует рассчитанное и пропущенное. | Стратифицированный dense workload, оценка компонентной обработки с контролем пропусков. |
| Идентичность и gateway | RBAC и tenant тестированы локально. Боевой OIDC/SSO, mTLS и проксирование bearer за shared Basic профилем требуют отдельной настройки. | Зарегистрированный IdP, проверенные issuer/audience/roles, private ingress, проверка revocation и claim mapping. |
| DB и аудит | Local grants и append-only включены в проверку. Cloud grants, независимый sink, retention и операционный monitoring остаются. | Отдельные principals в облаке, хранение и экспорт согласно политике банка, независимый reconciliation. |
| Docker и Railway | Docker API socket недоступен, Railway IaC статически проверен. Ни один cloud или image runtime не подтверждён. | Изолированный контейнерный runtime, Railway sandbox, container SBOM/digest/scanning, release identity. |
| Операции и регуляторика | HA, DR, подтверждённые RTO/RPO, длительный нагрузочный прогон, внешний security review, privacy assessment и согласования банка вне локальной проверки. | План восстановления с фактическим учением, модель угроз, санкционированная внешняя проверка, регуляторная оценка и runbooks. |

Следующий инженерный приоритет для команды BCC — получить изолированный sandbox и согласованный point-in-time holdout. Далее проверить реальный issuer и service credentials в sandbox, оценить recall и долю ошибочных предупреждений в shadow режиме, отдельно от исполнения денежных операций. [Реестр](ISSUE_RESOLUTION_REGISTER.csv)
