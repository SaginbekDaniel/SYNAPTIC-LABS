import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import excerpt from "./bench-excerpt.json";
import { BENCH, MISSED_TOTAL, MISSES, RECALL_COST, WORKLOAD_RATIO, share } from "./bench";

describe("results slide figures come from the committed holdout run", () => {
  it("the excerpt is a verbatim copy of benchmarks/results/bench-v1.json", () => {
    const src = JSON.parse(readFileSync(new URL("../../../../benchmarks/results/bench-v1.json", import.meta.url), "utf8"));
    expect(excerpt.code_commit).toBe(src.code.commit);
    expect(excerpt.code_dirty).toBe(false);
    expect(excerpt.datasets).toBe(src.splits.holdout.datasets);
    for (const m of ["nexora_v2", "B1_rules"] as const) {
      const r = src.results.holdout[m];
      expect(excerpt.results[m]).toEqual({ scenario: r.scenario, alerts: r.alerts, queue: r.queue, by_family: r.by_family });
    }
  });

  it("pins the displayed numbers", () => {
    expect(BENCH.datasets).toBe(30);
    expect(BENCH.suspicious + BENCH.legitimate).toBe(220);
    expect(BENCH.alertsPerDataset).toEqual({ rules: 42.57, nexora: 9.5 });
    expect(WORKLOAD_RATIO).toBe(4.5);
    expect(BENCH.legitFlagged.rules).toEqual({ n: 103, of: 128, pct: 80.5 });
    expect(BENCH.legitFlagged.nexora).toEqual({ n: 48, of: 128, pct: 37.5 });
    expect(BENCH.recall.rules).toEqual({ n: 88, of: 92, pct: 95.7 });
    // 73/92 = 79.348 %: computed from counts, not from the artifact's pre-rounded 0.7935 (which would give 79,4)
    expect(BENCH.recall.nexora).toEqual({ n: 73, of: 92, pct: 79.3 });
    expect(RECALL_COST).toBe(16.4);
  });

  it("percentages agree with the artifact's own ratios to within its 4-decimal rounding", () => {
    for (const m of ["nexora_v2", "B1_rules"] as const) {
      const s = excerpt.results[m].scenario;
      expect(Math.abs(share(s.tp, s.tp + s.fn) / 100 - s.recall)).toBeLessThan(0.001);
      expect(Math.abs(share(s.fp, s.fp + s.tn) / 100 - s.fpr)).toBeLessThan(0.001);
    }
  });

  it("the misses breakdown accounts for every false negative", () => {
    expect(MISSED_TOTAL).toBe(excerpt.results.nexora_v2.scenario.fn);
    expect(MISSES.map((f) => [f.id, f.missed, f.abstained])).toEqual([
      ["S1_collection_funnel", 9, 0],
      ["S1_collection_funnel_boundary", 8, 8],
      ["H_same_day_chain", 1, 0],
      ["S2_layering_chain", 1, 0],
    ]);
  });
});

import { QR } from "./qr";
import { REPO_URL } from "./links";
describe("finale QR code", () => {
  it("encodes the repository link shown next to it", () => expect(QR.url).toBe(REPO_URL));
});
