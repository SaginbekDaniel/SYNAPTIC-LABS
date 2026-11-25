import { describe, expect, it } from "vitest";
import type { EvaluationReport, MethodSummary } from "../../lib/types";
import bench from "../../../../../benchmarks/results/bench-v1.json";
import { countMetric, familyRows, formatMetric, isLegitimateFamily, methodMetrics, metricValue, num, numeratorMetric, recoveredMetric, storedMetric } from "./evaluationView";

// The committed benchmark run: the numbers the Evaluation screen serves.
const artifact = bench as unknown as EvaluationReport;

function summary(byFamily: Record<string, { total: number; flagged: number }>): MethodSummary {
  return {
    datasets: 1,
    scenario: { suspicious: 0, legitimate: 0, tp: 0, fp: 0, fn: 0, tn: 0, precision: null, recall: null, f1: null, fpr: null, fnr: null, surfaced_recall: null, high_band_recall: null, high_band_fpr: null },
    alerts: { flagged: 0, per_dataset: null, precision: null, unmatched: 0 },
    queue: { p_at_5: null, p_at_10: null, recall_at_5: null, recall_at_10: null },
    by_family: Object.fromEntries(Object.entries(byFamily).map(([k, v]) => [k, { ...v, surfaced: v.flagged }])),
    latency_ms: { median: null, p95: null, max: null },
  };
}

describe("evaluation view helpers", () => {
  it("formats ratios and never invents a value for missing metrics", () => {
    expect(formatMetric(countMetric(8, 15))).toBe("53,3 %");
    expect(formatMetric(countMetric(7, 7))).toBe("100,0 %");
    expect(formatMetric(countMetric(0, 0))).toBe("—");
    expect(formatMetric(storedMetric(null))).toBe("—");
    expect(num(undefined)).toBe("—");
  });
  it("separates legitimate look-alikes from suspicious families", () => {
    expect(isLegitimateFamily("N2_merchant_settlement")).toBe(true);
    expect(isLegitimateFamily("H_same_day_chain")).toBe(false);
    const rows = familyRows(
      { a: summary({ S4_circular_flow: { total: 7, flagged: 7 }, N7_treasury_sweep: { total: 8, flagged: 8 } }), b: summary({ S4_circular_flow: { total: 7, flagged: 5 } }) },
      ["a", "b"],
    );
    expect(rows.suspicious).toEqual([{ family: "S4_circular_flow", total: 7, flagged: { a: 7, b: 5 } }]);
    expect(rows.legitimate[0]?.flagged).toEqual({ a: 8, b: 0 });
  });
});

describe("benchmark metrics are rounded once, from counts", () => {
  const holdoutV2 = artifact.results.holdout!.nexora_v2!;

  it("shows NEXORA v2 holdout recall as 73/92 = 79,3 %, not the re-rounded stored 0.7935", () => {
    expect(holdoutV2.scenario.recall).toBe(0.7935);
    const m = methodMetrics(holdoutV2);
    expect(m.recall).toEqual({ kind: "count", num: 73, den: 92 });
    expect(formatMetric(m.recall)).toBe("79,3 %");
    // F1 = 2·73 / (2·73 + 48 + 19) = 68,545 % (stored, from counts, as 0.6854).
    expect(formatMetric(m.f1)).toBe("68,5 %");
    expect(formatMetric(m.precision)).toBe("60,3 %");
    expect(formatMetric(m.fpr)).toBe("37,5 %");
  });

  it("matches the counts for every summary in the committed artifact", () => {
    const summaries: MethodSummary[] = [
      ...Object.values(artifact.results).flatMap((r) => Object.values(r)),
      ...Object.values(artifact.ablations).flatMap((r) => Object.values(r)),
      ...(artifact.robustness ? [artifact.robustness.base, ...artifact.robustness.perturbations.map((p) => p.summary)] : []),
      ...(artifact.sensitivity?.variants.map((v) => v.summary) ?? []),
    ];
    expect(summaries.length).toBeGreaterThan(20);
    for (const s of summaries) {
      const { tp, fp, fn, tn } = s.scenario;
      const m = methodMetrics(s);
      expect(metricValue(m.recall)).toBeCloseTo(tp / (tp + fn), 12);
      expect(metricValue(m.fpr)).toBeCloseTo(fp / (fp + tn), 12);
      if (2 * tp + fp + fn > 0) expect(s.scenario.f1).toBe(Math.round((2 * tp * 1e4) / (2 * tp + fp + fn)) / 1e4);
      // Emitted numerators agree with what the legacy fallback recovers from the ratio.
      for (const [count, ratio, den] of [
        [s.scenario.tp_high, s.scenario.high_band_recall, s.scenario.suspicious],
        [s.scenario.fp_high, s.scenario.high_band_fpr, s.scenario.legitimate],
        [s.alerts.relevant, s.alerts.precision, s.alerts.flagged],
      ] as const) {
        expect(count).not.toBeUndefined();
        if (count !== null && count !== undefined) expect(recoveredMetric(ratio, den)).toEqual(countMetric(count, den));
      }
      // Ratios with a known denominator resolve to an exact count that rounds back to the stored value.
      for (const [metric, stored] of [
        [m.highFpr, s.scenario.high_band_fpr],
        [m.alertPrecision, s.alerts.precision],
      ] as const) {
        if (stored === null) expect(metric.kind).toBe("none");
        else {
          expect(metric.kind).toBe("count");
          expect(metricValue(metric)).toBeCloseTo(stored, 4);
        }
      }
    }
  });

  it("prefers emitted numerators and recovers them from the ratio only for older artifacts", () => {
    // Emitted count wins, even where the ratio alone could not identify it (den ≥ 10^4).
    expect(numeratorMetric(3, 20000, 0.0002)).toEqual({ kind: "count", num: 3, den: 20000 });
    expect(numeratorMetric(0, 7, 0)).toEqual({ kind: "count", num: 0, den: 7 });
    // Older artifact: no count field → recovered from the stored ratio.
    expect(numeratorMetric(undefined, 128, 0.0625)).toEqual({ kind: "count", num: 8, den: 128 });
    expect(numeratorMetric(null, 7, 0.5)).toEqual({ kind: "stored", ratio: 0.5 });
    expect(numeratorMetric(null, 7, null)).toEqual({ kind: "none" });
    // methodMetrics reads the count fields when present and ignores a contradicting ratio.
    const legacy = structuredClone(holdoutV2);
    const withCounts = { ...legacy, scenario: { ...legacy.scenario, fp_high: 1, high_band_fpr: 0.9 }, alerts: { ...legacy.alerts, relevant: 2 } };
    expect(methodMetrics(withCounts).highFpr).toEqual({ kind: "count", num: 1, den: legacy.scenario.legitimate });
    expect(methodMetrics(withCounts).alertPrecision).toEqual({ kind: "count", num: 2, den: legacy.alerts.flagged });
  });

  it("recovers the numerator of a stored ratio only when it is unique and consistent", () => {
    // 0.0625 is stored for 8/128; 0.3474 for 99/285.
    expect(recoveredMetric(0.0625, 128)).toEqual({ kind: "count", num: 8, den: 128 });
    expect(recoveredMetric(0.3474, 285)).toEqual({ kind: "count", num: 99, den: 285 });
    // No numerator over 7 rounds to 0.5: keep the stored value rather than invent a count.
    expect(recoveredMetric(0.5, 7)).toEqual({ kind: "stored", ratio: 0.5 });
    expect(recoveredMetric(null, 7)).toEqual({ kind: "none" });
  });

  it("shows ratios without counts (queue means) at the precision the artifact holds", () => {
    // 0.4775 may be a mean anywhere in [0.47745, 0.47755): one decimal would be a guess.
    expect(formatMetric(storedMetric(0.4775))).toBe("47,75 %");
    expect(formatMetric(storedMetric(0.4828))).toBe("48,28 %");
    expect(formatMetric(storedMetric(0.6))).toBe("60,00 %");
    expect(methodMetrics(holdoutV2).p5).toEqual({ kind: "stored", ratio: holdoutV2.queue.p_at_5 });
  });

  it("derives alerts per dataset from the alert count", () => {
    expect(methodMetrics(holdoutV2).alertsPerDataset).toBe(holdoutV2.alerts.flagged / holdoutV2.datasets);
  });
});

describe("error example grouping", () => {
  it("collapses identical cases and keeps the priority range", async () => {
    const { groupExamples } = await import("./evaluationView");
    const row = (family: string, priority: number | null, explanation: "alerted" | "abstained" = "alerted") => ({
      dataset: "d", scenario_id: `${family}-${priority}`, family, difficulty: "hard", notes: "", kind: "funnel", band: "medium", priority, reasons: [], explanation,
    });
    const groups = groupExamples([row("N2", 62), row("N2", 65), row("N7", 58), row("N2", null, "abstained")]);
    expect(groups[0]).toMatchObject({ family: "N2", count: 2, priorities: [62, 65], bands: ["medium"] });
    expect(groups).toHaveLength(3);
  });
});
