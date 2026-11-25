# Transfer Protection V2

В sandbox реализован generic pre-transaction контракт POST /api/v1/sandbox/transfers. Тело включает intent ID, beneficiary, сумму в minor units, ISO currency, время запроса и канал. Customer reference берётся из проверенной идентичности. Intent ID действует как ключ повтора в пространстве tenant и субъекта. Assessment привязан к tenant и автору. Reviewer открывает оригинальную запись по UUID. Старые публичные presets продолжают обслуживать прежний демонстрационный сценарий.

## Контекст и доказательства

Point-in-time adapter принимает cutoff и возвращает состояние источника, доступные версии профилей и safe source refs. Детерминированные fixture profiles покрывают доверенного получателя, высокий риск, неизвестный профиль и недоступность. Будущая или устаревшая информация исключается контрактом провайдера. Первая запись сохраняет policy version, timestamp, risk band, доступность, evidence и безопасный customer message. Повторное обращение с тем же intent ID возвращает эту запись. Изменённый payload с тем же intent ID конфликтует. Явная повторная оценка после отказа связывается с исходным UUID.

## Решение и действие

| Слой | Наблюдаемое состояние |
|---|---|
| Assessment | ALLOW, WARN, STEP_UP, LIMITED_SIGNAL, UNAVAILABLE |
| Обновление sandbox | Подтверждение, проверка, ручное решение reviewer, отмена или повторная оценка |
| Ack | Append-only acknowledgement с actor, action ID и результатом симуляции |
| История | Persisted assessment, policy и evidence доступны после перезагрузки |

Один серверный lock сериализует действия на одном assessment. Повтор действия идемпотентен. Низкая доступность сигналов и отказ источника остаются видимыми пользователю, действие в таких состояниях ограничено. Для тестовой эмуляции проверки используется sandbox confirmation, а для банка нужен внешний SCA и подтверждение платёжного состояния.

Локальный preflight подтвердил ALLOW на раннем cutoff, STEP_UP при доступности позднего сигнала, UNAVAILABLE при отказе источника, открытие reviewer evidence и ack SIMULATED_COMPLETED. Playwright подтвердил перезагрузку URL, шаг проверки и итоговое отображение. Идентичность sandbox хранится в памяти страницы и после обновления предъявляется заново. Технический результат на прежних 112 intents остался 29 TP, 5 FP, 62 TN, 16 FN. Precision 85,29%, recall 64,44% и FPR 7,46%. Улучшилась исполнимость и наблюдаемость сценария sandbox. Цели по качеству прежней политики не достигнуты.

[Preflight](evidence/release-preflight.json) · [Browser](evidence/final-browser.log) · [Transfer holdout](evidence/transfer-holdout-final.json) · [Интеграционные тесты](../../tests/integration/test_versioned_transfer_sandbox.py)
