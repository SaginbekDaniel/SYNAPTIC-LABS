/**
 * Localisation. All user-facing copy lives here; components never hard-code strings.
 * Russian is the product language (spec §0). Adding a locale = adding a dictionary with
 * the same keys (enforced by the `Messages` type).
 */
import type { ReasonCode } from "./types";
import { formatBp, formatMoney } from "./format";

const ru = {
  "app.name": "NEXORA AI",
  "app.team": "SYNAPTIC LABS",
  "app.simulation": "СИМУЛЯЦИЯ",
  "app.simulationHint": "Синтетические данные. Нет подключения к банку.",
  "app.demoMode": "Демо-режим · аналитик: {actor}",
  "app.disclaimer": "Автоматическая приоритизация для проверки аналитиком, а не вывод о противоправных действиях.",
  "nav.command": "Обзор",
  "nav.alerts": "Алерты",
  "nav.network": "Граф связей",
  "nav.cases": "Кейсы",
  "nav.lab": "Fraud Lab",
  "nav.primary": "Основная навигация",
  "dataset.label": "Набор данных",
  "dataset.none": "Нет наборов данных",
  "dataset.pick": "Выберите набор данных",
  "dataset.snapshot": "Снимок {id} · {date}",
  "dataset.noSnapshot": "Анализ ещё не выполнялся",
  "dataset.tx": "{count} {count|транзакция|транзакции|транзакций}",
  "state.loading": "Загрузка…",
  "state.retry": "Повторить",
  "state.error": "Не удалось загрузить данные",
  "state.errorCode": "Код: {code} · запрос {rid}",
  "state.network": "Сервер недоступен. Проверьте, что API запущен.",
  "state.empty": "Нет данных",
  "state.noDatasetTitle": "Нет активного набора данных",
  "state.noDatasetBody": "Создайте синтетический сценарий в Fraud Lab, чтобы начать.",
  "state.toLab": "Открыть Fraud Lab",
  "common.open": "Открыть",
  "common.cancel": "Отмена",
  "common.save": "Сохранить",
  "common.account": "Счёт",
  "common.amount": "Сумма",
  "common.date": "Дата",
  "common.from": "Отправитель",
  "common.to": "Получатель",
  "common.status": "Статус",
  "common.txId": "ID транзакции",
  "common.precision": "Точность времени",
  "common.precisionDay": "только дата",
  "common.precisionTimestamp": "точное время",
  "common.precisionMixed": "смешанная",
  "common.yes": "да",
  "common.no": "нет",
  "common.showAll": "Показать все ({count})",
  "common.showLess": "Свернуть",
  "command.title": "Обзор",
  "command.subtitle": "Состояние анализа активного набора данных. Все показатели берутся из сохранённого снимка.",
  "command.transactions": "Транзакций в снимке",
  "command.accounts": "Счетов в графе",
  "command.formations": "Формаций найдено",
  "command.openAlerts": "Открытых алертов",
  "command.cases": "Кейсов",
  "command.snapshot": "Снимок графа",
  "command.excluded": "исключено (не проведены): {count}",
  "command.byBand": "Открытые алерты по приоритету",
  "command.temporal": "Хронологическая проверка формаций",
  "command.provenance": "Происхождение снимка",
  "command.inputHash": "Хэш входных данных",
  "command.configHash": "Хэш конфигурации",
  "command.policy": "Политика риска",
  "command.window": "Окно наблюдения",
  "command.partial": "Снимок частичный: {reasons}",
  "command.job": "Последняя задача анализа",
  "alerts.title": "Очередь алертов",
  "alerts.subtitle": "Гипотезы о сетевых формациях, ранжированные для проверки. Приоритет — порядок работы, а не вероятность мошенничества.",
  "alerts.filterBand": "Приоритет",
  "alerts.filterKind": "Тип формации",
  "alerts.filterStatus": "Статус",
  "alerts.all": "Все",
  "alerts.empty": "Алертов нет",
  "alerts.emptyHint": "Для этого набора данных нет алертов с заданными фильтрами. Запустите анализ в Fraud Lab.",
  "alerts.accounts": "{count} {count|счёт|счёта|счетов}",
  "alerts.evidence": "{count} {count|доказательство|доказательства|доказательств}",
  "alerts.transactions": "{count} {count|транзакция|транзакции|транзакций}",
  "alerts.notInLatest": "нет в последнем снимке",
  "alerts.revision": "ревизия {n}",
  "alerts.total": "Всего: {count}",
  "alerts.inCase": "в кейсе",
  "alerts.open": "открыт",
  "alerts.closed": "закрыт",
  "kind.funnel": "Воронка сбора средств",
  "kind.chain": "Цепочка транзитных переводов",
  "kind.funnelShort": "воронка",
  "kind.chainShort": "цепочка",
  "band.critical": "Критический",
  "band.high": "Высокий",
  "band.medium": "Средний",
  "band.low": "Низкий",
  "band.insufficient_evidence": "Недостаточно данных",
  "ev.supported": "Хронология подтверждена",
  "ev.possible_ambiguous": "Порядок неоднозначен",
  "ev.contradicted": "Хронология противоречит",
  "ev.unavailable": "Проверка недоступна",
  "alert.hypothesis": "Гипотеза",
  "alert.hypothesis.funnel": "{feeders} {feeders|счёт направил|счёта направили|счетов направили} основную часть своих исходящих средств на счёт {center}; {downstream}",
  "alert.hypothesis.funnelDown": "далее средства уходили на {count} {count|счёт|счёта|счетов}.",
  "alert.hypothesis.funnelNoDown": "дальнейшее движение средств не наблюдается.",
  "alert.hypothesis.chain": "Средства проходили через {hops} {hops|последовательный перевод|последовательных перевода|последовательных переводов} от {from} к {to}.",
  "alert.reasons": "Основания",
  "alert.reasonsHint": "Каждое основание выведено из сохранённых числовых наблюдений.",
  "alert.priority": "Приоритет",
  "alert.priorityHint": "Эвристика для очереди (0–100), не вероятность.",
  "alert.families": "Подтверждающие семейства сигналов",
  "alert.missingFamilies": "Не измерено: {list}",
  "alert.graph": "Формация",
  "alert.graphHint": "Строится только из транзакций-доказательств. Толщина ребра — сумма.",
  "alert.evidenceTx": "Транзакции-доказательства",
  "alert.evidenceTxHint": "Исходные записи, на которых основан алерт. Нажмите на основание, чтобы выделить его транзакции.",
  "alert.temporal": "Хронология и совместимость сумм",
  "alert.temporalHint": "Максимальный поток с учётом порядка дат и сумм; одна сумма не может быть учтена дважды.",
  "alert.counter": "Контраргументы и ограничения",
  "alert.counterHint": "Что ослабляет гипотезу или не наблюдается в данных.",
  "alert.dataRequests": "Рекомендуемые запросы данных",
  "alert.dataRequestsHint": "Задачи для уполномоченного аналитика, не автоматический сбор данных.",
  "alert.noDataRequests": "Дополнительные данные не требуются для текущей гипотезы.",
  "alert.provenance": "Происхождение",
  "alert.detector": "Детектор",
  "alert.snapshot": "Снимок",
  "alert.thresholds": "Пороги",
  "alert.highlightTx": "Показать транзакции",
  "alert.highlighted": "Выделено: {count}",
  "alert.clearHighlight": "Снять выделение",
  "temporal.entry": "Вход в формацию",
  "temporal.strict": "Подтверждённо совместимо",
  "temporal.possible": "С учётом переводов одного дня",
  "temporal.share": "Доля входа",
  "temporal.lag": "Задержка между звеньями",
  "temporal.lagDays": "{min}–{max} дн.",
  "temporal.lagSeconds": "{min}–{max} с",
  "temporal.noLag": "—",
  "temporal.uncertain": "Неупорядоченных переходов",
  "temporal.precision": "Точность источника",
  "case.title": "Расследование",
  "case.open": "Открыть кейс",
  "case.opening": "Открытие…",
  "case.status": "Статус кейса",
  "case.version": "версия {n}",
  "case.assigned": "Ответственный",
  "case.decision": "Решение аналитика",
  "case.noDecision": "Решение ещё не принято",
  "case.action": "Действие",
  "case.reason": "Обоснование",
  "case.reasonRequired": "Обоснование обязательно для этого действия",
  "case.submit": "Записать решение",
  "case.saving": "Сохранение…",
  "case.conflict": "Кейс изменён другим аналитиком. Данные обновлены — проверьте и повторите.",
  "case.humanOnly": "Решение фиксируется только в журнале. Система не блокирует счета и не отправляет сообщения.",
  "case.notes": "Заметки",
  "case.notePlaceholder": "Заметка для журнала расследования",
  "case.addNote": "Добавить заметку",
  "case.noNotes": "Заметок пока нет",
  "case.audit": "Журнал аудита",
  "case.auditHint": "Только добавление: записи нельзя изменить или удалить.",
  "case.noCase": "Кейс по этому алерту ещё не открыт.",
  "case.listTitle": "Кейсы",
  "case.listSubtitle": "Расследования, открытые аналитиками.",
  "case.empty": "Кейсов пока нет. Откройте кейс из карточки алерта.",
  "case.opened": "Открыт",
  "cs.new": "Новый",
  "cs.investigating": "В работе",
  "cs.escalated": "Эскалирован",
  "cs.dismissed": "Отклонён",
  "cs.closed": "Закрыт",
  "cs.reopened": "Переоткрыт",
  "act.investigating": "Взять в работу",
  "act.escalated": "Эскалировать",
  "act.dismissed": "Отклонить гипотезу",
  "act.closed": "Закрыть",
  "act.reopened": "Переоткрыть",
  "audit.case.opened": "Кейс открыт",
  "audit.case.investigating": "Взят в работу",
  "audit.case.escalated": "Эскалирован",
  "audit.case.dismissed": "Гипотеза отклонена",
  "audit.case.closed": "Закрыт",
  "audit.case.reopened": "Переоткрыт",
  "audit.case.note_added": "Добавлена заметка",
  "network.title": "Граф связей",
  "network.subtitle": "Ограниченная окрестность любого счёта в текущем снимке. Поиск по точному идентификатору.",
  "network.search": "Идентификатор счёта",
  "network.depth": "Глубина",
  "network.go": "Показать",
  "network.notFound": "Счёт {id} не найден в снимке {snapshot}.",
  "network.truncated": "Показана часть окрестности: достигнут лимит {nodes} {nodes|узел|узла|узлов} / {edges} {edges|ребро|ребра|рёбер}.",
  "network.summary": "Сводка по счёту",
  "network.in": "Входящие",
  "network.out": "Исходящие",
  "network.counterparties": "{count} {count|контрагент|контрагента|контрагентов}",
  "network.formations": "Участие в формациях",
  "network.noFormations": "Счёт не входит ни в одну обнаруженную формацию.",
  "network.boundary": "на границе выборки",
  "network.edges": "Связи",
  "network.selectEdge": "Выберите связь, чтобы увидеть транзакции",
  "network.edgeTx": "Транзакции {from} → {to}",
  "network.role.subject": "центр",
  "network.role.member": "участник",
  "network.role.exit": "выход",
  "network.hint": "Введите идентификатор счёта или откройте счёт из алерта.",
  "graph.legend.subject": "Центр / конечная точка",
  "graph.legend.entry": "Вход",
  "graph.legend.exit": "Выход",
  "graph.legend.member": "Участник",
  "graph.legend.boundary": "Граница наблюдения",
  "graph.alt": "Граф {nodes} счетов и {edges} связей. Табличная версия — ниже.",
  "lab.title": "Fraud Lab",
  "lab.subtitle": "Синтетические сценарии: подозрительные формации и легитимные двойники. Метки сценариев не передаются детекторам.",
  "lab.suite": "Набор сценариев",
  "lab.seed": "Seed",
  "lab.precision": "Точность времени",
  "lab.generate": "Сгенерировать набор",
  "lab.generating": "Генерация…",
  "lab.analyse": "Запустить анализ",
  "lab.analysing": "Анализ…",
  "lab.steps": "Конвейер",
  "lab.step1": "Генерация и импорт транзакций",
  "lab.step2": "Задача анализа в очереди",
  "lab.step3": "Снимок опубликован воркером",
  "lab.step4": "Алерты готовы к проверке",
  "lab.report": "Отчёт импорта",
  "lab.accepted": "Принято",
  "lab.duplicates": "Дубликаты",
  "lab.quarantined": "Карантин",
  "lab.warnings": "Предупреждения",
  "lab.jobStatus": "Статус задачи: {status}",
  "lab.jobWaiting": "Задача ожидает воркер. Убедитесь, что процесс воркера запущен.",
  "lab.jobFailed": "Анализ завершился ошибкой: {code}",
  "lab.toAlerts": "Перейти к алертам ({count})",
  "lab.families": "Сценарии в наборе",
  "lab.datasets": "Наборы данных",
  "lab.use": "Сделать активным",
  "lab.active": "активный",
  "job.queued": "в очереди",
  "job.running": "выполняется",
  "job.succeeded": "готово",
  "job.failed": "ошибка",
  "job.cancelled": "отменено",
  "family.S1_collection_funnel": "S1 · Сбор и перераспределение (подозрительный)",
  "family.S2_layering_chain": "S2 · Многоступенчатая цепочка (подозрительный)",
  "family.H_same_day_chain": "H · Цепочка в один день (неоднозначная хронология)",
  "family.S1_collection_funnel_boundary": "H · Воронка на границе выборки",
  "family.N1_payroll": "N1 · Выплата зарплаты (легитимный)",
  "family.N2_merchant_settlement": "N2 · Расчёты эквайера (легитимный)",
  "family.N4_reimbursement": "N4 · Взаимные возмещения (легитимный)",
  "family.N8_reverse_chronology_chain": "N8 · Обратная хронология (легитимный)",
  "lim.missing_context": "Нет данных о владельцах и назначении платежей",
  "lim.timestamp_precision_limited": "Источник содержит только даты, без времени",
  "lim.boundary_limited": "Часть счетов на границе выборки: дальнейшее движение не наблюдается",
  "lim.upstream_unknown": "Источники поступлений не наблюдаются",
  "lim.downstream_unobserved": "Исходящие переводы центра не наблюдаются — удержание средств не доказано",
  "lim.structural_only": "Структурное наблюдение без учёта времени",
  "lim.path_does_not_prove_same_funds": "Путь в графе не доказывает перемещение тех же средств",
  "lim.same_day_order_unresolved": "Порядок переводов внутри одного дня не установлен",
  "lim.identical_timestamps": "Совпадающие отметки времени",
  "lim.chronology_rules_out_flow": "Даты исключают предполагаемое движение средств",
  "lim.insufficient_compatible_amount": "Хронологически совместима лишь малая часть суммы",
  "lim.day_precision_no_intraday_order": "Внутридневной порядок неизвестен",
  "lim.intermediary_balances_unobserved": "Остатки промежуточных счетов неизвестны — источник средств не идентифицирован",
  "lim.missing_leg": "Отсутствует звено цепочки",
  "lim.currency_mix": "Разные валюты без данных о конвертации",
  "lim.flow_budget_exceeded": "Превышен вычислительный лимит проверки",
  "lim.transfer_reused_across_layers": "Транзакция повторно использована в разных звеньях",
  "nbdr.outgoing_history_beyond_boundary": "Исходящие переводы счёта за пределами границы выборки",
  "nbdr.outgoing_history_for_center": "Исходящие переводы центрального счёта",
  "nbdr.incoming_history_for_entry_accounts": "История поступлений на входные счета",
  "nbdr.exact_timestamps": "Точное время для переводов одного дня",
  "nbdr.res.determine_onward_movement": "Установить, куда ушли средства",
  "nbdr.res.identify_funding_sources": "Установить источники средств",
  "nbdr.res.order_same_day_transfers": "Упорядочить переводы внутри дня",
  "nbdr.window": "Период: {from} — {to}",
  "nbdr.subjects": "Объекты: {count}",
  "reason.STRUCT_FUNNEL_FEEDERS": "{count} {count|различный счёт направил|различных счёта направили|различных счетов направили} основную часть исходящих средств одному получателю: всего {total}.",
  "reason.STRUCT_CHAIN_PATH": "Обнаружен путь из {hops} {hops|последовательного перевода|последовательных переводов|последовательных переводов} через транзитные счета.",
  "reason.TEMPORAL_PASS_THROUGH_SUPPORTED": "Хронологически совместимо дальнейшее перечисление {amount} ({share} поступлений), задержка {lag}",
  "reason.TEMPORAL_PATH_SUPPORTED": "Подтверждена хронологически совместимая последовательность: {amount} ({share} входа), задержка между звеньями {lag}",
  "reason.TEMPORAL_SAME_DAY_AMBIGUOUS": "Для {count} {count|перехода|переходов|переходов} доступна только дата; порядок внутри дня не подтверждён.",
  "reason.TEMPORAL_CONTRADICTED": "Даты переводов противоречат гипотезе: совместимо лишь {share} суммы.",
  "reason.TEMPORAL_UNAVAILABLE": "Хронологическая проверка невозможна: {reason}.",
  "reason.COVERAGE_BOUNDARY": "Наблюдение прекращается на границе выборки ({count} {count|счёт|счёта|счетов}); дальнейший маршрут неизвестен.",
  "reason.COVERAGE_DOWNSTREAM_UNOBSERVED": "Исходящие переводы центрального счёта не наблюдаются.",
  "reason.COVERAGE_UPSTREAM_UNKNOWN": "Источники поступлений не наблюдаются.",
  "reason.COVERAGE_DAY_PRECISION": "Источник содержит только даты: скорость перевода в часах не вычисляется.",
  "reason.NO_SUPPORTED_SIGNAL": "Нет подтверждённых сигналов для приоритизации.",
  "reason.NO_INDEPENDENT_CORROBORATION": "Нет независимого подтверждения из другого семейства сигналов.",
  "reason.BAND_CAPPED_BY_EVIDENCE": "Приоритет ограничен: «{from}» → «{to}» из-за качества доказательств.",
  "reason.unknown": "Основание {code}",
  "family.STRUCTURE": "структура",
  "family.TEMPORAL": "хронология",
  "family.PEER_STATISTICS": "сравнение с группой",
  "family.NETWORK_CONTEXT": "сетевой контекст",
  "lag.sameDay": "в тот же день",
  "lag.days": "{min}–{max} дн.",
  "lag.day": "{n} дн.",
} as const;

export type MessageKey = keyof typeof ru;
type Params = Record<string, string | number>;
export type Messages = Record<MessageKey, string>;

const dictionaries: Record<string, Messages> = { ru };
let active: Messages = ru;

export function setLocale(locale: string): void {
  active = dictionaries[locale] ?? ru;
}

const pluralRules = new Intl.PluralRules("ru-RU");
const PLURAL_INDEX: Record<string, number> = { one: 0, few: 1, many: 2, other: 2 };

/** `{n|form1|form2|form5}` selects a Russian plural form for param `n`. */
function plural(n: number, forms: string[]): string {
  const idx = Number.isInteger(n) ? (PLURAL_INDEX[pluralRules.select(n)] ?? 2) : 1;
  return forms[Math.min(idx, forms.length - 1)] ?? "";
}

export function t(key: MessageKey, params?: Params): string {
  const template = active[key] ?? key;
  if (!params) return template;
  return template
    .replace(/\{(\w+)\|([^}]+)\}/g, (_, name: string, forms: string) => plural(Number(params[name]), forms.split("|")))
    .replace(/\{(\w+)\}/g, (_, name: string) => (name in params ? String(params[name]) : `{${name}}`));
}

export function hasKey(key: string): key is MessageKey {
  return key in active;
}

export function tDynamic(prefix: string, value: string, fallback?: string): string {
  const key = `${prefix}${value}`;
  return hasKey(key) ? t(key) : (fallback ?? value);
}

function lagText(min: unknown, max: unknown): string {
  if (typeof min !== "number" || typeof max !== "number") return t("temporal.noLag");
  if (max === 0) return t("lag.sameDay");
  return min === max ? t("lag.day", { n: min }) : t("lag.days", { min, max });
}

/** Render a structured reason code to text from its validated numeric params only. */
export function reasonText(rc: ReasonCode, currency = "KZT"): string {
  const p = rc.params as Record<string, unknown>;
  switch (rc.code) {
    case "STRUCT_FUNNEL_FEEDERS":
      return t("reason.STRUCT_FUNNEL_FEEDERS", { count: Number(p.count), total: formatMoney(String(p.total_minor), currency) });
    case "STRUCT_CHAIN_PATH":
      return t("reason.STRUCT_CHAIN_PATH", { hops: Number(p.hops) });
    case "TEMPORAL_PASS_THROUGH_SUPPORTED":
    case "TEMPORAL_PATH_SUPPORTED":
      return t(`reason.${rc.code}` as MessageKey, {
        amount: formatMoney(String(p.compatible_minor), currency),
        share: formatBp(Number(p.fraction_bp)),
        lag: lagText(p.lag_days_min, p.lag_days_max),
      });
    case "TEMPORAL_SAME_DAY_AMBIGUOUS":
      return t("reason.TEMPORAL_SAME_DAY_AMBIGUOUS", { count: Number(p.uncertain_count) });
    case "TEMPORAL_CONTRADICTED":
      return t("reason.TEMPORAL_CONTRADICTED", { share: formatBp(Number(p.fraction_bp)) });
    case "TEMPORAL_UNAVAILABLE":
      return t("reason.TEMPORAL_UNAVAILABLE", { reason: tDynamic("lim.", String(p.reason)) });
    case "COVERAGE_BOUNDARY":
      return t("reason.COVERAGE_BOUNDARY", { count: Array.isArray(p.accounts) ? p.accounts.length : 0 });
    case "BAND_CAPPED_BY_EVIDENCE":
      return t("reason.BAND_CAPPED_BY_EVIDENCE", {
        from: tDynamic("band.", String(p.from)),
        to: tDynamic("band.", String(p.to)),
      });
    default:
      return hasKey(`reason.${rc.code}`) ? t(`reason.${rc.code}` as MessageKey) : t("reason.unknown", { code: rc.code });
  }
}

/** Direction of a reason relative to the hypothesis, for visual grouping. */
export function reasonPolarity(code: string): "for" | "against" | "limit" {
  if (code.startsWith("STRUCT_") || code.endsWith("_SUPPORTED")) return "for";
  if (code === "TEMPORAL_CONTRADICTED") return "against";
  return "limit";
}

export function precisionLabel(p: string): string {
  if (p === "day") return t("common.precisionDay");
  if (p === "timestamp") return t("common.precisionTimestamp");
  return t("common.precisionMixed");
}
