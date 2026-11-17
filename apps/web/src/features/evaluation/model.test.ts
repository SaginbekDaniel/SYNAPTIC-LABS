import { describe, expect, it } from "vitest";
import type { BenchmarkReport } from "../../lib/types";
import { comparatorMethod, defaultSplit, familyGroups, parseOutcomeReason, parseTransitions, primaryMethod, resultsForSplit } from "./model";

const report = {
  methods: [
    { name: "B0_volume", group: "baseline", description: "", config_sha256: null, threshold: 1 },
    { name: "B4_v1_structural_temporal", group: "nexora", description: "", config_sha256: "a", threshold: null },
    { name: "B5_v2_full", group: "nexora", description: "", config_sha256: "b", threshold: null },
  ],
  run: { splits_evaluated: ["dev", "val"] },
  results: [
    { split: "dev", method: "B5_v2_full" },
    { split: "dev", method: "B0_volume" },
    { split: "val", method: "B0_volume" },
  ],
  suite: {
    families: [
      { name: "P1", label: "suspicious", group: "suspicious", description: "" },
      { name: "N1", label: "benign", group: "benign", description: "" },
      { name: "P2", label: "suspicious", group: "suspicious", description: "" },
    ],
  },
} as unknown as BenchmarkReport;

describe("evaluation model", () => {
  it("compares the latest engine with the one recorded before it", () => {
    expect(primaryMethod(report)).toBe("B5_v2_full");
    expect(comparatorMethod(report)).toBe("B4_v1_structural_temporal");
  });

  it("defaults to the held-out split only when it was evaluated", () => {
    expect(defaultSplit(report)).toBe("val");
    expect(defaultSplit({ ...report, run: { ...report.run, splits_evaluated: ["dev", "val", "test"] } })).toBe("test");
  });

  it("orders rows by recorded method order, filtered by split", () => {
    expect(resultsForSplit(report, "dev").map((r) => r.method)).toEqual(["B0_volume", "B5_v2_full"]);
  });

  it("parses outcome transitions and reasons without losing counts", () => {
    expect(parseTransitions({ "N1_merchant_settlement: TN->FP": 8, "P2: FN->TP": 2 })).toEqual([
      { family: "N1_merchant_settlement", from: "TN", to: "FP", count: 8 },
      { family: "P2", from: "FN", to: "TP", count: 2 },
    ]);
    expect(parseOutcomeReason("alerted:funnel+chain")).toEqual({ outcome: "alerted", kinds: ["funnel", "chain"] });
    expect(parseOutcomeReason("abstained")).toEqual({ outcome: "abstained", kinds: [] });
  });

  it("groups families in benchmark order", () => {
    expect(familyGroups(report)).toEqual([
      { group: "suspicious", families: ["P1", "P2"] },
      { group: "benign", families: ["N1"] },
    ]);
  });
});
