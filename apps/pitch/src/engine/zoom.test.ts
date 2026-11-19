import { describe, expect, it } from "vitest";
import { viewFor } from "./zoom";

describe("viewFor", () => {
  it("fits and centres without a region", () => {
    const v = viewFor(1000, 500, 1600, 1000);
    expect(v.s).toBeCloseTo(0.5);
    expect(v.x).toBeCloseTo(100);
    expect(v.y).toBeCloseTo(0);
  });
  it("never zooms beyond the cap and never exposes empty space", () => {
    const v = viewFor(1000, 500, 1600, 1000, { x: 0.9, y: 0.9, w: 0.05, h: 0.05 }, 1.4);
    expect(v.s).toBeLessThanOrEqual(1.4);
    expect(v.x).toBeLessThanOrEqual(0);
    expect(v.x).toBeGreaterThanOrEqual(1000 - 1600 * v.s);
    expect(v.y).toBeGreaterThanOrEqual(500 - 1000 * v.s);
  });
});
