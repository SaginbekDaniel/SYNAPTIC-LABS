import { describe, expect, it } from "vitest";
import { evaluate, partition, statusOf } from "./hypotheses";

describe("hypothesis scoring (documented rules)", () => {
  it("statuses follow the documented thresholds", () => {
    expect(statusOf([1, 1, 0, 0])).toBe("supported");
    expect(statusOf([1, 1, -1, 0])).toBe("weakened");
    expect(statusOf([0, -1, -1, 0])).toBe("refuted");
    expect(statusOf([1, 0, 0, 0])).toBe("not_established");
  });

  it("dataset A favours the suspicious explanation", () => {
    const e = evaluate("A");
    expect(e.status.suspicious).toBe("supported");
    expect(e.status.legit).toBe("refuted");
    expect(e.verdict).toBe("suspicious_explanation_favoured");
  });

  it("dataset B favours the benign explanation (the single gate that lowers priority)", () => {
    const e = evaluate("B");
    expect(e.status.legit).toBe("supported");
    expect(e.balance.suspicious).toBeLessThan(0);
    expect(e.verdict).toBe("benign_explanation_favoured");
  });

  it("every observation lands in exactly one bucket", () => {
    for (const ds of ["A", "B"] as const)
      for (const h of ["suspicious", "legit"] as const) {
        const p = partition(ds, h);
        expect(p.supports.length + p.contradicts.length + p.neutral.length).toBe(4);
      }
  });
});
