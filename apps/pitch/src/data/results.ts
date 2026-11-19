import excerpt from "./sealed-excerpt.json";

/**
 * Every number on slide 5 is derived from the committed sealed-v1 artifact (excerpted verbatim in
 * sealed-excerpt.json). Nothing is typed in by hand; rounding is the only transformation.
 */
export interface Metric {
  key: "fpr" | "recall" | "p5" | "hbfpr";
  title: string;
  hint: string;
  lowerIsBetter: boolean;
  before: number; // percent
  after: number; // percent
  delta: number; // percentage points
  ci: [number, number]; // percentage points
}

const pct = (x: number) => Math.round(x * 1000) / 10; // 0.5072 -> 50.7
const b = excerpt.bootstrap;
const mk = (key: Metric["key"], title: string, hint: string, lowerIsBetter: boolean, src: { baseline: number; candidate: number; difference: number; ci95: number[] }): Metric => ({
  key, title, hint, lowerIsBetter,
  before: pct(src.baseline), after: pct(src.candidate),
  delta: pct(src.difference), ci: [pct(src.ci95[0]), pct(src.ci95[1])],
});

export const METRICS: Metric[] = [
  mk("fpr", "Ложные срабатывания", "Легитимные сети, помеченные как подозрительные", true, b.fpr),
  mk("recall", "Полнота", "Подозрительные сети, которые найдены", false, b.recall),
  mk("p5", "Полезные алерты в топ‑5", "Доля реальных сетей среди первых пяти (distinct P@5)", false, b.distinct_p_at_5),
  mk("hbfpr", "Ложные при высоком приоритете", "Легитимные сети в полосе «Высокий»", true, b.high_band_fpr),
];

export const META = {
  datasets: excerpt.datasets,
  split: excerpt.split,
  outcome: excerpt.decision.outcome,
  commit: excerpt.code_commit.slice(0, 7),
};

export const signed = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1).replace(".", ",")}`;
export const num = (n: number) => n.toFixed(1).replace(".", ",");
