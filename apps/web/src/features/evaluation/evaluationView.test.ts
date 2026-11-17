import { describe, expect, it } from "vitest";
import type { MethodSummary } from "../../lib/types";
import { familyRows, isLegitimateFamily, num, pct } from "./evaluationView";

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
    expect(pct(0.5333)).toBe("53,3 %");
    expect(pct(1)).toBe("100 %");
    expect(pct(null)).toBe("—");
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
