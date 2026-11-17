import type { BenchmarkReport, MethodSplitResult } from "../../lib/types";

/** The engine shown in the headline: the last NEXORA method recorded in the run. */
export function primaryMethod(report: BenchmarkReport): string | null {
  const nexora = report.methods.filter((m) => m.group === "nexora");
  return nexora.length ? nexora[nexora.length - 1]!.name : null;
}

/** The engine it is compared against: the NEXORA method recorded just before it. */
export function comparatorMethod(report: BenchmarkReport): string | null {
  const nexora = report.methods.filter((m) => m.group === "nexora");
  return nexora.length > 1 ? nexora[nexora.length - 2]!.name : null;
}

/** Prefer the held-out test split when it was evaluated, else the last evaluated split. */
export function defaultSplit(report: BenchmarkReport): string {
  const splits = report.run.splits_evaluated;
  return splits.includes("test") ? "test" : (splits[splits.length - 1] ?? "dev");
}

export function resultFor(report: BenchmarkReport, split: string, method: string | null): MethodSplitResult | undefined {
  return method ? report.results.find((r) => r.split === split && r.method === method) : undefined;
}

export function resultsForSplit(report: BenchmarkReport, split: string): MethodSplitResult[] {
  const order = new Map(report.methods.map((m, i) => [m.name, i]));
  return report.results.filter((r) => r.split === split).sort((a, b) => (order.get(a.method) ?? 0) - (order.get(b.method) ?? 0));
}

export interface Transition {
  family: string;
  from: string;
  to: string;
  count: number;
}

/** "P1_mule_collection: TP->FN" → structured, so the UI can label family and outcomes. */
export function parseTransitions(map: Record<string, number>): Transition[] {
  return Object.entries(map)
    .map(([key, count]) => {
      const [family = key, move = ""] = key.split(": ");
      const [from = "", to = ""] = move.split("->");
      return { family, from, to, count };
    })
    .sort((a, b) => b.count - a.count || a.family.localeCompare(b.family));
}

/** "alerted:funnel+chain" → { outcome: "alerted", kinds: ["funnel", "chain"] }. */
export function parseOutcomeReason(reason: string): { outcome: string; kinds: string[] } {
  const [outcome = reason, kinds = ""] = reason.split(":");
  return { outcome, kinds: kinds ? kinds.split("+") : [] };
}

/** Families grouped in benchmark order: suspicious, benign, hard negatives. */
export function familyGroups(report: BenchmarkReport): { group: string; families: string[] }[] {
  const groups: { group: string; families: string[] }[] = [];
  for (const f of report.suite.families) {
    let g = groups.find((x) => x.group === f.group);
    if (!g) {
      g = { group: f.group, families: [] };
      groups.push(g);
    }
    g.families.push(f.name);
  }
  return groups;
}
