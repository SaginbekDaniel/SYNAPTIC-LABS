import { describe, expect, it } from "vitest";
import { METRICS, META, signed } from "./results";

describe("slide 5 metrics come from the sealed artifact", () => {
  const m = Object.fromEntries(METRICS.map((x) => [x.key, x]));
  it("match the published figures", () => {
    expect([m.fpr.before, m.fpr.after]).toEqual([50.7, 15.9]);
    expect([m.recall.before, m.recall.after]).toEqual([73.3, 74.8]);
    expect([m.p5.before, m.p5.after]).toEqual([46.5, 59.3]);
    expect([m.hbfpr.before, m.hbfpr.after]).toEqual([17.8, 9.8]);
  });
  it("is the pre-registered improvement on 60 datasets", () => {
    expect(META.datasets).toBe(60);
    expect(META.outcome).toBe("improvement");
  });
  it("formats signed deltas with a real minus", () => {
    expect(signed(-34.8)).toBe("−34,8");
    expect(signed(1.5)).toBe("+1,5");
  });
});
