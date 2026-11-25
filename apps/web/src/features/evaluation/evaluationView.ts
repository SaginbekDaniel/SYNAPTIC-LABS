import type { EvaluationReport, MethodSummary } from "../../lib/types";

type ErrorExample = NonNullable<EvaluationReport["examples"]>["false_positives"][number];

export const SPLIT_ORDER = ["holdout", "validation", "dev"] as const;

/**
 * A displayed benchmark metric. The artifact stores every ratio rounded to 4 decimals, so
 * rounding a stored ratio again to one percent decimal can produce a wrong digit
 * (73/92 = 79.348 % is stored as 0.7935 → "79,4 %"). Ratios are therefore shown from their
 * integer counts whenever the artifact has them; a ratio with no counts behind it (queue
 * means over datasets) is shown exactly as stored, at the 2 percent decimals it holds.
 */
export type Metric =
  | { kind: "count"; num: number; den: number }
  | { kind: "stored"; ratio: number }
  | { kind: "none" };

const NONE: Metric = { kind: "none" };
const STORED_DECIMALS = 4;

export function countMetric(num: number, den: number): Metric {
  return den > 0 ? { kind: "count", num, den } : NONE;
}

export function storedMetric(ratio: number | null | undefined): Metric {
  return ratio === null || ratio === undefined ? NONE : { kind: "stored", ratio };
}

/**
 * Integer numerator behind a stored ratio whose denominator is known. A 4-decimal ratio
 * identifies its numerator uniquely while den < 10^4 (neighbouring numerators are more than
 * 10^-4 apart); the candidate is verified to round back to the stored value, else the
 * stored ratio is kept as is.
 */
export function recoveredMetric(ratio: number | null | undefined, den: number): Metric {
  if (ratio === null || ratio === undefined) return NONE;
  if (den <= 0 || den >= 10 ** STORED_DECIMALS) return storedMetric(ratio);
  const num = Math.round(ratio * den);
  const half = 0.5 / 10 ** STORED_DECIMALS + Number.EPSILON;
  return num >= 0 && num <= den && Math.abs(num / den - ratio) <= half ? countMetric(num, den) : storedMetric(ratio);
}

/**
 * A ratio whose numerator the artifact emits as an integer (bench-harness artifacts after
 * `tp_high` / `fp_high` / `alerts.relevant` were added). Artifacts written before that only
 * carry the rounded ratio, so the numerator is recovered from it as a fallback.
 */
export function numeratorMetric(num: number | null | undefined, den: number, ratio: number | null | undefined): Metric {
  return num === null || num === undefined ? recoveredMetric(ratio, den) : countMetric(num, den);
}

/** The metric as a fraction in [0, 1] for bar geometry, or null when undefined. */
export function metricValue(m: Metric): number | null {
  return m.kind === "count" ? m.num / m.den : m.kind === "stored" ? m.ratio : null;
}

/** "79,3 %" from counts (rounded once), "48,28 %" for a stored-only ratio, "—" when undefined. */
export function formatMetric(m: Metric): string {
  // Integer arithmetic for counts: num·1000/den is exact at a true tie, so rounding happens once.
  if (m.kind === "count") return percent(Math.round((m.num * 1000) / m.den) / 10, 1);
  if (m.kind === "stored") return percent(Math.round(m.ratio * 10 ** STORED_DECIMALS) / 100, STORED_DECIMALS - 2);
  return "—";
}

// Fixed decimals: a column of metrics stays aligned and "60,00 %" says the value is known to 0.01.
function percent(value: number, digits: number): string {
  return `${value.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
}

export interface MethodMetrics {
  precision: Metric;
  recall: Metric;
  f1: Metric;
  fpr: Metric;
  highFpr: Metric;
  alertPrecision: Metric;
  /** Queue metrics are means over datasets: no counts exist behind them. */
  p5: Metric;
  /** Distinct planted networks among the first five alerts (audit L-02); "none" in older artifacts. */
  p5Distinct: Metric;
  r5: Metric;
  /** Alerts per dataset, from the alert count (the stored value is rounded to 2 decimals). */
  alertsPerDataset: number | null;
}

/** Every percentage the Evaluation screen shows for one method, from counts where they exist. */
export function methodMetrics(s: MethodSummary): MethodMetrics {
  const { tp, fp, fn, tn, legitimate } = s.scenario;
  return {
    precision: countMetric(tp, tp + fp),
    recall: countMetric(tp, tp + fn),
    // F1 = 2tp / (2tp + fp + fn), rounded once here rather than re-rounding the stored 4-decimal f1.
    f1: countMetric(2 * tp, 2 * tp + fp + fn),
    fpr: countMetric(fp, fp + tn),
    highFpr: numeratorMetric(s.scenario.fp_high, legitimate, s.scenario.high_band_fpr),
    alertPrecision: numeratorMetric(s.alerts.relevant, s.alerts.flagged, s.alerts.precision),
    p5: storedMetric(s.queue.p_at_5),
    p5Distinct: storedMetric(s.queue.distinct_p_at_5),
    r5: storedMetric(s.queue.recall_at_5),
    alertsPerDataset: s.datasets > 0 ? s.alerts.flagged / s.datasets : null,
  };
}

export function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("ru-RU", { maximumFractionDigits: digits });
}

/** Default to the most trustworthy split present: holdout, then validation, then dev. */
export function defaultSplit(report: EvaluationReport): string | null {
  return SPLIT_ORDER.find((s) => s in report.results) ?? Object.keys(report.results)[0] ?? null;
}

/**
 * Scenario families follow the generator convention: legitimate families start with "N";
 * every other family (S*, H*) is a planted suspicious or deliberately hard case.
 */
export function isLegitimateFamily(family: string): boolean {
  return family.startsWith("N");
}

export interface FamilyRow {
  family: string;
  total: number;
  flagged: Record<string, number>;
}

export function familyRows(results: Record<string, MethodSummary>, methods: readonly string[]): { suspicious: FamilyRow[]; legitimate: FamilyRow[] } {
  const base = results[methods[0] ?? ""];
  const rows: FamilyRow[] = Object.entries(base?.by_family ?? {}).map(([family, c]) => ({
    family,
    total: c.total,
    flagged: Object.fromEntries(methods.map((m) => [m, results[m]?.by_family[family]?.flagged ?? 0])),
  }));
  return {
    suspicious: rows.filter((r) => !isLegitimateFamily(r.family)),
    legitimate: rows.filter((r) => isLegitimateFamily(r.family)),
  };
}

export interface ExampleGroup {
  key: string;
  family: string;
  kind: string | null | undefined;
  explanation: ErrorExample["explanation"];
  count: number;
  bands: string[];
  priorities: number[];
}

/** Collapse repeated error cases (same family, formation kind and explanation) into one row with a count. */
export function groupExamples(rows: readonly ErrorExample[]): ExampleGroup[] {
  const groups = new Map<string, ExampleGroup>();
  for (const r of rows) {
    const key = `${r.family}|${r.kind ?? ""}|${r.explanation}`;
    const g = groups.get(key) ?? { key, family: r.family, kind: r.kind, explanation: r.explanation, count: 0, bands: [], priorities: [] };
    g.count += 1;
    if (r.band && !g.bands.includes(r.band)) g.bands.push(r.band);
    if (r.priority !== null && r.priority !== undefined) g.priorities.push(r.priority);
    groups.set(key, g);
  }
  return [...groups.values()].sort((a, b) => b.count - a.count || a.family.localeCompare(b.family));
}
