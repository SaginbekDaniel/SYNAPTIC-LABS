import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import excerpt from "./bench-excerpt.json";
import { BENCH, FAMILIES, WORKLOAD_CUT, WORKLOAD_RATIO } from "./bench";

describe("slide 5 figures come from the committed holdout run", () => {
  it("the excerpt is a verbatim copy of benchmarks/results/bench-v1.json", () => {
    const src = JSON.parse(readFileSync(new URL("../../../../benchmarks/results/bench-v1.json", import.meta.url), "utf8"));
    expect(excerpt.code_commit).toBe(src.code.commit);
    expect(excerpt.code_dirty).toBe(false);
    for (const m of ["nexora_v2", "B1_rules"] as const) {
      const r = src.results.holdout[m];
      expect(excerpt.results[m]).toEqual({ scenario: r.scenario, alerts: r.alerts, queue: r.queue, by_family: r.by_family });
    }
  });
  it("pins the displayed numbers", () => {
    expect(BENCH.datasets).toBe(30);
    expect(BENCH.alertsPerDataset).toEqual({ rules: 42.57, nexora: 9.5 });
    expect(WORKLOAD_CUT).toBe(78);
    expect(WORKLOAD_RATIO).toBe(4.5);
    expect(BENCH.fpr).toEqual({ rules: 80.5, nexora: 37.5 });
    expect(BENCH.recall).toEqual({ rules: 95.7, nexora: 79.4 });
    expect(BENCH.surfacedRecall).toBe(88);
    expect(BENCH.p5).toEqual({ rules: 32.7, nexora: 48.3 });
  });
  it("covers every scenario family exactly once and the totals add up", () => {
    expect(FAMILIES.length).toBe(Object.keys(excerpt.results.nexora_v2.by_family).length);
    const sum = (k: "legit" | "suspicious") => FAMILIES.filter((f) => f.kind === k).reduce((a, f) => a + f.total, 0);
    expect(sum("legit")).toBe(BENCH.legitimate);
    expect(sum("suspicious")).toBe(BENCH.suspicious);
    const fp = FAMILIES.filter((f) => f.kind === "legit").reduce((a, f) => a + f.nexora, 0);
    expect(fp).toBe(excerpt.results.nexora_v2.scenario.fp);
  });
});

import { QR } from "./qr";
import { REPO_URL } from "./links";
describe("finale QR code", () => {
  it("encodes the repository link shown next to it", () => expect(QR.url).toBe(REPO_URL));
});
