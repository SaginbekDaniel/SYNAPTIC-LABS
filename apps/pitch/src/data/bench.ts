import excerpt from "./bench-excerpt.json";

/**
 * Results slide: NEXORA (risk-policy-v2) against per-account monitoring rules (baseline B1) on the holdout split
 * of the committed benchmark run. bench-excerpt.json is a verbatim copy produced by scripts/extract-bench.mjs.
 *
 * Every percentage is computed from the confusion counts (tp/fn/fp/tn), never from the artifact's pre-rounded
 * ratios: 73/92 = 79.35 % is 79,3 %, whereas rounding the stored 0.7935 again would give 79,4 %.
 *
 * Deliberately NOT exported (see docs, PR #3 audit): surfaced recall (boundary abstentions leak labels in bench-v1,
 * L-01) and P@K (counts duplicate alerts on one network, L-02).
 */
const nx = excerpt.results.nexora_v2;
const rules = excerpt.results.B1_rules;

/** Share in percent, one decimal, half-up on the exact ratio. */
export const share = (num: number, den: number) => Math.round((num / den) * 1000) / 10;
/** Russian decimal comma. */
export const dec = (n: number, d = 1) => n.toFixed(d).replace(".", ",");

interface Counts { tp: number; fp: number; fn: number; tn: number }
const recallOf = (s: Counts) => share(s.tp, s.tp + s.fn);
const fprOf = (s: Counts) => share(s.fp, s.fp + s.tn);

export const BENCH = {
  datasets: excerpt.datasets,
  commit: excerpt.code_commit.slice(0, 7),
  suspicious: nx.scenario.suspicious,
  legitimate: nx.scenario.legitimate,
  alertsPerDataset: { rules: rules.alerts.per_dataset, nexora: nx.alerts.per_dataset },
  /** legitimate networks with at least one alert in the queue */
  legitFlagged: {
    rules: { n: rules.scenario.fp, of: rules.scenario.fp + rules.scenario.tn, pct: fprOf(rules.scenario) },
    nexora: { n: nx.scenario.fp, of: nx.scenario.fp + nx.scenario.tn, pct: fprOf(nx.scenario) },
  },
  /** planted suspicious networks flagged (recall) — "insufficient evidence" is NOT counted as found */
  recall: {
    rules: { n: rules.scenario.tp, of: rules.scenario.tp + rules.scenario.fn, pct: recallOf(rules.scenario) },
    nexora: { n: nx.scenario.tp, of: nx.scenario.tp + nx.scenario.fn, pct: recallOf(nx.scenario) },
  },
};

/** How many times shorter NEXORA's queue is than the rules' queue, one decimal. */
export const WORKLOAD_RATIO = Math.round((BENCH.alertsPerDataset.rules / BENCH.alertsPerDataset.nexora) * 10) / 10;

/** Recall given up, in percentage points (positive number). */
export const RECALL_COST = Math.round((BENCH.recall.rules.pct - BENCH.recall.nexora.pct) * 10) / 10;

export interface Miss { id: string; label: string; missed: number; total: number; abstained: number }

const MISS_LABELS: Record<string, string> = {
  S1_collection_funnel: "Воронка сбора",
  S1_collection_funnel_boundary: "Воронка на границе выгрузки",
  S2_layering_chain: "Цепочка транзитных счетов",
  H_same_day_chain: "Цепочка в пределах одного дня",
};

/**
 * Where NEXORA's misses are: every suspicious family with at least one planted network not flagged.
 * `abstained` = shown to the analyst as "insufficient evidence" (not counted as found).
 */
export const MISSES: Miss[] = Object.entries(nx.by_family)
  .filter(([id]) => /^(S|H)/.test(id))
  .map(([id, f]) => ({ id, label: MISS_LABELS[id] ?? id, total: f.total, missed: f.total - f.flagged, abstained: f.surfaced - f.flagged }))
  .filter((f) => f.missed > 0)
  .sort((a, b) => b.missed - a.missed || a.id.localeCompare(b.id));

export const MISSED_TOTAL = MISSES.reduce((a, f) => a + f.missed, 0);
