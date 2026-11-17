import type { EvaluationReport, MethodSummary } from "../../lib/types";

type ErrorExample = NonNullable<EvaluationReport["examples"]>["false_positives"][number];

export const SPLIT_ORDER = ["holdout", "validation", "dev"] as const;

/** Metric in [0, 1] (or null when undefined for a method) → "53,3 %" / "—". */
export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(Math.round(value * 1000) / 10).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} %`;
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
