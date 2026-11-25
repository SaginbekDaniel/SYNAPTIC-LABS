# Проверка детекции и защиты перевода

Аудит 25 ноября 2026 года · `43368ff46b788568d34ceee5ac8ae9135728c373` · только синтетические операции.

## Как работает детекция

Batch pipeline строит directed graph по валютам из posted transfers. Cancelled/reversed исключены из расчёта. Funnel ищет концентрацию независимых отправителей, fan-out — распределение, cycle — замыкание направленных путей, chain — многозвенные переводы со сходными объёмами. Temporal flow решает ограниченную задачу integer max-flow с chronology и capacity. Peer Statistics сравнивает концентрацию оборота в трёхдневном окне с Tukey IQR для наблюдаемых аналогов. При малом cohort возможен fallback или abstention. Сигналы обрабатывает rule engine на фиксированном YAML. В системе нет обучаемых параметров, inference ML и LLM. [Pipeline](../src/nexora/analytics/pipeline.py#L715) · [Temporal](../src/nexora/analytics/temporal/flow.py#L91) · [Peer](../src/nexora/analytics/statistical/peer.py#L96)

Policy учитывает по одному сильнейшему сигналу каждого семейства. Веса Structure 0,35, Temporal 0,30, Peer 0,20 и Network Context 0,15. Последнее семейство batch pipeline не выпускает, поэтому потолок расчёта 85 при strength ≤1. Формула `clip(round(100 × Σ(weight × strength)), 0, 100)` формирует triage priority. Medium от 30 и одного supported, high от 45 и двух, critical от 80 и трёх. Затем применяются evidence caps и отказ от оценки для ограниченного subject. Неоднозначная хронология может дать ненулевой вклад и ограничивает band. `insufficient_evidence` в продукте виден как watch, в binary оценке ниже исключён из flagged. Пороги заданы вручную и исследованы на собственной synthetic validation. [Policy](../configs/risk_policy.yaml) · [Scoring](../src/nexora/analytics/risk.py#L32)

Штатный rerun восстановил invariance для shuffle и 5% точных повторов. При случайной потере 10% строк recall validation упал с 76,8% до 60,7%. Смена `max_hop_lag_days` с 7 на 5 и 10 изменила recall 76,8% → 71,4% и 87,5%, FPR 42,3% → 36,5% и 47,1%. При ±1% jitter amounts aggregate recall validation сохранился, high-band FPR изменился с 10,6% до 12,9%. Coverage abstention и peer counterevidence сдерживают эскалацию и снижают часть recall. [Benchmark JSON](evidence/bench-v1-rerun.json)

Аудит проверил evidence refs на существующие accounts и transactions, отсутствие quarantine и стабильность output при развороте порядка строк для 31 сценария. Штатный API test пересчитывает сумму по возвращённым source transfers. Причины содержат типологии, temporal статус, coverage и запросы на данные. Вывод об источнике денег требует дополнительной информации о балансе и реальном пути средств. Одинаковый высокий балл для легитимного lookalike с корректными доказательствами обосновывает форму графа, но не преступное намерение. Для LLM-галлюцинаций и prompt injection компонент отсутствует.

## Воспроизведение опубликованных чисел

В чистом снимке этой ветки выполнены оба CLI. Совпали сравниваемые поля за вычетом метаданных времени, elapsed/latency, среды и Git provenance. У опубликованного benchmark исходная ревизия `58440cc19285`, у Transfer — `1652880ccfb`. Совпали counts, split/manifest hashes, thresholds, robustness/ablations и classifiers. NEXORA v2 зафиксировал holdout 30 datasets и 220 networks. [bench-v1](evidence/bench-v1-rerun.json) · [Transfer holdout](evidence/transfer-holdout-rerun.json) · [Сравнение](evidence/benchmark-comparison.json)

| Holdout · network | TP/FP/TN/FN | Precision | Recall | F1 | FPR | Alerts/dataset |
|---|---:|---:|---:|---:|---:|---:|
| NEXORA v2 | 73/48/80/19 | 60,3% | 79,3% | 68,6% | 37,5% | 9,50 |
| NEXORA v1 в harness | 56/59/69/36 | 48,7% | 60,9% | 54,1% | 46,1% | 7,30 |
| B4 structure + temporal | 73/43/85/19 | 62,9% | 79,3% | 70,2% | 33,6% | 8,83 |
| B3 structure only | 92/95/33/0 | 49,2% | 100% | 66,0% | 74,2% | 57,93 |
| B1 monitoring rules | 88/103/25/4 | 46,1% | 95,7% | 62,2% | 80,5% | 42,57 |
| B0 turnover | 61/64/64/31 | 48,8% | 66,3% | 56,2% | 50,0% | 9,50 |
| B2 PageRank | 7/58/70/85 | 10,8% | 7,6% | 8,9% | 45,3% | 9,50 |

NEXORA v2 high-band FPR 6,25%, recall 64,13%. Precision отдельных алертов 34,74% из 285 flagged items. P@5 48,28%, R@5 73,61%, P@10 41,96%, R@10 87,22% по очередям. Медиана pure pipeline v2 33,3 мс, P95 66,4 мс на audit host. 21 из 21 settlements и 12 из 12 treasury sweeps получили хотя бы medium. 8 из 8 boundary funnels остались ниже порога. Числа относятся к генератору команды, включающему dev/validation/holdout по seed и заранее описанные hard negatives.

| Transfer holdout · 112 intents (45 fraud, 67 legitimate) | TP/FP/TN/FN | Precision | Recall | FPR |
|---|---:|---:|---:|---:|
| NEXORA Transfer | 29/5/62/16 | 85,29% | 64,44% | 7,46% |
| Amount only | 15/36/31/30 | 29,41% | 33,33% | 53,73% |
| First-time recipient | 32/39/28/13 | 45,07% | 71,11% | 58,21% |
| Graph only | 31/32/35/14 | 49,21% | 68,89% | 47,76% |

Transfer F1 73,42%, FNR 35,56%, 74,6 ложных предупреждений на 1 000 legitimate intents, 12,50% `LIMITED_SIGNAL`, 3,57% `UNAVAILABLE`. При условной независимости строк 95% Wilson для recall около 50–77%, для FPR 3–16%. Повторяющиеся рецепты уменьшают эффективный размер выборки. Одиннадцать fraud misses пришлись на limited/stale/ошибку зависимости, ещё пять — на slow collection. Тайминг CLI измеряет policy inference в памяти. WARN/STEP_UP считаются вмешательством в оценке. Данных о предотвращённом ущербе нет.

## Независимые сценарии

31 handcrafted fixture написан отдельно от project generator. Для 20 fraud ожидался минимум medium, для 11 legitimate — отсутствие флага. Взят наблюдаемый ledger с exact timestamps, лейблы и деловой контекст хранятся вне входа. Для binary оценки low и watch исключены. Для каждой строки JSON сохраняет вход, ground truth, subject accounts, evidence accounts и transfer IDs, band/priority/reason codes и FP/FN на трёх уровнях. Сценарии без достаточного сигнала — диагностические продуктовые пропуски. [Входы и выходы](evidence/independent-fraud.json)

| № | Сценарий | Ожидание | Факт · band/приоритет | Результат |
|---:|---|---|---|---|
| 1 | Круговой перевод | alert | cycle high 51 | PASS |
| 2 | Сеть мулов | alert | funnel high 58 | PASS |
| 3 | Быстрый транзит | alert | chain high 51 | PASS |
| 4 | Fan-in без downstream | alert | funnel medium 30 | PASS |
| 5 | Fan-out | alert | fan_out high 47 | PASS |
| 6 | Multi-hop | alert | chain high 65 | PASS |
| 7 | Structuring | alert | нет formation | FN |
| 8 | Smurfing без контекста наличных | alert | funnel medium 35 | PASS |
| 9 | Резкая смена поведения | alert | нет formation | FN |
| 10 | Необычная сумма | alert | нет formation | FN |
| 11 | Активация спящего счёта | alert | нет formation | FN |
| 12 | Координация без общих счетов | alert | нет formation | FN |
| 13 | Подозрительный посредник | alert | chain high 51 | PASS |
| 14 | Fraud chain | alert | chain high 58 | PASS |
| 15 | Повторные подозрительные переводы | alert | нет formation | FN |
| 16 | Риск получателя вне ledger | alert | нет formation | FN |
| 17 | Account takeover | alert | нет formation | FN |
| 18 | Социальная инженерия | alert | нет formation | FN |
| 19 | Смешанная сеть | alert | cycle high 51 | PASS |
| 20 | Неизвестный cross-currency chain | alert | нет formation | FN |
| 21 | Зарплата | без alert | fan_out high 47 | FP |
| 22 | Семейный перевод | без alert | нет formation | PASS |
| 23 | Платежи бизнеса | без alert | chain high 65 | FP |
| 24 | Merchant settlement | без alert | funnel high 58 | FP |
| 25 | Погашение кредитов | без alert | funnel medium 35 | FP |
| 26 | Совместные расходы | без alert | нет formation | PASS |
| 27 | Marketplace | без alert | fan_out high 47 | FP |
| 28 | Легитимный high-volume | без alert | funnel high 56 | FP |
| 29 | Подписки | без alert | нет formation | PASS |
| 30 | Возвраты | без alert | cycle high 51 | FP |
| 31 | Переводы между своими счетами | без alert | нет formation | PASS |

**Итог — 10/20 fraud обнаружены, 7/11 legitimate выдали false alert.** Mule/merchant settlement имеют один ledger и одинаковый high 58. Salary/fan-out — high 47, business/multi-hop — high 65, refunds/circular — high 51. Family, takeover и social engineering используют одинаковый единичный ledger. Ни один не формирует alert. Ground truth mixed case отделяет две legitimate операции от cycle. Межвалютный chain разделён детектором на валютные графы. Для takeover и social engineering нужны признаки устройства, сессии и доверенный клиентский контекст. Для structuring, dormant, unusual amount и повторов нужны история, каналы и правила агрегации. Smurfing был отмечен по topology, вывод о канале внесения средств недоступен.

### Смешанные наборы с различной prevalence

Три seed 7101, 7193, 7283 на каждую долю. Каждый dataset содержит 100 групп. Типы берутся с возвращением, время и суммы варьируются, повторяющиеся шаблоны зависимы. Группы разделены по account namespace. Policy зафиксирована без подбора на этих данных. Alert subject даёт account flag, formation transaction IDs дают transaction attribution, network flag означает хотя бы один alert subject группы. Метрики transaction/account характеризуют attribution метода, у которого исходная единица — формация. Ранжирование по максимальному priority с нулём за отсутствующие и tie-break по идентификатору. AUC/AP вычислены по seed и усреднены. Precision/recall/F1/FPR используют pooled counts. Wilson в JSON — справочный интервал с допущением независимости.

| Prevalence | Единица NEXORA | TP/FP/TN/FN | Precision | Recall | F1 | FPR | AP / ROC AUC | P@10 / R@10 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1% | network | 1/194/103/2 | 0,51% | 33,33% | 1,01% | 65,32% | 4,83 / 43,94% | 3,33 / 33,33% |
| 1% | account | 1/194/1588/10 | 0,51% | 9,09% | 0,97% | 10,89% | 1,25 / 47,60% | 3,33 / 5,56% |
| 1% | transaction | 5/1288/351/12 | 0,39% | 29,41% | 0,76% | 78,58% | 4,92 / 39,37% | 0 / 0% |
| 5% | network | 7/185/100/8 | 3,65% | 46,67% | 6,76% | 64,91% | 6,10 / 44,00% | 6,67 / 13,33% |
| 5% | account | 7/185/1503/92 | 3,65% | 7,07% | 4,81% | 10,96% | 5,70 / 49,46% | 6,67 / 2,31% |
| 5% | transaction | 32/1214/339/62 | 2,57% | 34,04% | 4,78% | 78,17% | 5,79 / 28,93% | 0 / 0% |
| 20% | network | 30/162/78/30 | 15,62% | 50,00% | 23,81% | 67,50% | 21,21 / 44,04% | 26,67 / 13,33% |
| 20% | account | 30/162/1301/280 | 15,62% | 9,68% | 11,95% | 11,07% | 18,01 / 49,52% | 26,67 / 2,75% |
| 20% | transaction | 145/1076/272/117 | 11,88% | 55,34% | 19,55% | 79,82% | 17,05 / 39,18% | 33,33 / 4,07% |

FNR равен 100% минус recall. При prevalence 1% было только три fraud networks на все seed. Один hit дал 33,33%. Медианные pure latencies по трём seed 32,39, 30,98 и 30,54 мс для 1/5/20%. Объём 63–67, 63–65 и 63–65 alerts на 100 groups соответственно.

| F1 на network · фиксированные baselines | 1% fraud | 5% fraud | 20% fraud |
|---|---:|---:|---:|
| NEXORA | 1,01% | 6,76% | 23,81% |
| Хотя бы одна операция ≥5 000 000 minor units | 1,27% | 7,19% | 28,84% |
| Basic graph с ≥5 разными контрагентами | 0% | 2,44% | 10,78% |

Amount baseline применяет единый диагностический threshold без FX. При большом числе lookalikes baseline объёма дал лучший F1. Переносимость на банковский поток требует внешних данных и заранее заданных критериев.

### Внешний публичный sample

Из официального `IBM/AMLSim` на `7338a4bcb1af9bcfea2201ad7daccfe2a4d569ca` прочитаны `sample/outputs/tx.csv` и `alerts.csv` под лицензией репозитория Apache-2.0. 45 строк, 27 account IDs, два размеченных alert subjects. Суммы переданы без масштабирования с допущением USD minor units. Day index переводится в дату по условной оси без выдуманного точного времени. 88 cash rows исключены из-за отсутствия обычного counterparty. NEXORA выдал 0 formations и обнаружил 0/2 помеченных subjects. Максимальная сумма 19 827 minor units, ниже типовых порогов графа. Малый sample, неоднозначная семантика направления и неполная разметка не дают корректной precision/FPR. Авторский полный набор IBM AML Data использует CDLA-Sharing-1.0. Прямой запрос конкретного файла Kaggle вернул 404, полный набор в расчёт не вошёл. [IBM AMLSim sample](https://github.com/IBM/AMLSim/tree/7338a4bcb1af9bcfea2201ad7daccfe2a4d569ca/sample/outputs) · [IBM AML-Data](https://github.com/IBM/AML-Data) · [Лог и хеши](evidence/external-amlsim.json)

## Pre-transaction и customer protection

| Возможность | Что проверено | Что нужно в банке |
|---|---|---|
| Preflight / beneficiary risk | API пересчитывает правило по подготовленному профилю. Replay early → ALLOW, поздний профиль → STEP_UP. | Привязать live intent, идентификатор получателя, свежий профиль, consented telemetry и происхождение сигнала. |
| Предупреждение / подтверждение | WARN предлагает сверку реквизитов и официальную поддержку. Завершение симуляции хранится в UI. | Customer intervention endpoint, SCA/step-up, доступные сообщения, исполняемое подтверждение и серверное состояние. |
| Рекомендация специалисту / hold | STEP_UP и объяснения отделены analyst token. CASE существует для batch alert. Payment hold отсутствует. | Идемпотентный hold/release, статус, ручное решение, события и audit actor claims. |
| Realtime / отказ | Обнаружение сетей batch. Transfer check отвечает по готовому профилю. Kill switch и fixture outage проверены, browser offline retry восстановился. | Event stream, свежесть, политика degraded/fail mode, мониторинг времени ответа и потерянных сигналов. |
| Feedback | Batch case outcome и аудит сохраняются. Политика их не читает. | Проверенные outcomes, shadow evaluation, регулярная калибровка и оценка потерь. |
