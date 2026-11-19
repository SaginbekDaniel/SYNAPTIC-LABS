import excerpt from "./bench-excerpt.json";

/**
 * Slide 5: NEXORA (risk-policy-v2, in main) against classic per-account monitoring rules (baseline B1) on the
 * frozen holdout split of the committed benchmark run. bench-excerpt.json is a verbatim copy produced by
 * scripts/extract-bench.mjs; nothing here is typed in by hand, rounding is the only transformation.
 */
const nx = excerpt.results.nexora_v2;
const rules = excerpt.results.B1_rules;

export const pct = (x: number) => Math.round(x * 1000) / 10; // 0.8047 -> 80.5
export const dec = (n: number, d = 1) => n.toFixed(d).replace(".", ",");

export const BENCH = {
  datasets: excerpt.datasets,
  commit: excerpt.code_commit.slice(0, 7),
  suspicious: nx.scenario.suspicious,
  legitimate: nx.scenario.legitimate,
  alertsPerDataset: { rules: rules.alerts.per_dataset, nexora: nx.alerts.per_dataset },
  fpr: { rules: pct(rules.scenario.fpr), nexora: pct(nx.scenario.fpr) },
  recall: { rules: pct(rules.scenario.recall), nexora: pct(nx.scenario.recall) },
  surfacedRecall: pct(nx.scenario.surfaced_recall),
  p5: { rules: pct(rules.queue.p_at_5), nexora: pct(nx.queue.p_at_5) },
  highBandFpr: pct(nx.scenario.high_band_fpr),
};

/** How many times shorter NEXORA's queue is than the rules' queue, one decimal. */
export const WORKLOAD_RATIO = Math.round((BENCH.alertsPerDataset.rules / BENCH.alertsPerDataset.nexora) * 10) / 10;

/** Share of the rules' review queue that NEXORA removes, in percent (rounded to whole). */
export const WORKLOAD_CUT = Math.round((1 - BENCH.alertsPerDataset.nexora / BENCH.alertsPerDataset.rules) * 100);

export type FamilyKind = "legit" | "suspicious";
export interface Family {
  id: string;
  kind: FamilyKind;
  label: string;
  total: number;
  rules: number; // scenarios flagged by monitoring rules
  nexora: number; // scenarios flagged by NEXORA
  nexoraSurfaced: number; // flagged + shown as "insufficient evidence"
}

/** Russian names for the synthetic scenario families. Order = display order (legitimate first). */
const LABELS: Record<string, [FamilyKind, string]> = {
  N1_payroll: ["legit", "Зарплатные выплаты"],
  N6_loan_repayments: ["legit", "Погашение займов"],
  N4_reimbursement: ["legit", "Возмещение расходов"],
  N8_reverse_chronology_chain: ["legit", "Обратная хронология"],
  N3_supplier_payments: ["legit", "Оплата поставщикам"],
  N5_family_remittance: ["legit", "Семейные переводы"],
  N2_merchant_settlement: ["legit", "Расчёты с мерчантами"],
  N7_treasury_sweep: ["legit", "Казначейские переводы"],
  S3_coordinated_distribution: ["suspicious", "Скоординированная раздача"],
  S4_circular_flow: ["suspicious", "Круговой поток"],
  S5_scatter_gather: ["suspicious", "Раздача и сбор"],
  S3_distribution_terminal: ["suspicious", "Раздача на конечный счёт"],
  S2_layering_chain: ["suspicious", "Цепочка транзитных счетов"],
  H_same_day_chain: ["suspicious", "Цепочка в один день"],
  S1_collection_funnel: ["suspicious", "Воронка сбора"],
  S1_collection_funnel_boundary: ["suspicious", "Воронка на границе данных"],
};

export const FAMILIES: Family[] = Object.entries(LABELS).map(([id, [kind, label]]) => {
  const n = nx.by_family[id as keyof typeof nx.by_family];
  const r = rules.by_family[id as keyof typeof rules.by_family];
  return { id, kind, label, total: n.total, rules: r.flagged, nexora: n.flagged, nexoraSurfaced: n.surfaced };
});
