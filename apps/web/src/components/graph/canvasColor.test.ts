import { describe, expect, it } from "vitest";
import { toCanvasColor } from "./canvasColor";

describe("toCanvasColor", () => {
  it("rewrites CSS Color 4 rgb() into the comma form Cytoscape parses", () => {
    expect(toCanvasColor("rgb(163 167 200 / 0.38)")).toBe("rgba(163, 167, 200, 0.38)");
    expect(toCanvasColor(" rgb(84 89 114 / 42%) ")).toBe("rgba(84, 89, 114, 0.42)");
    expect(toCanvasColor("rgb(10 20 30)")).toBe("rgb(10, 20, 30)");
    expect(toCanvasColor("rgb(100% 0% 50%)")).toBe("rgb(255, 0, 128)");
  });

  it("normalises legacy forms and leaves other notations untouched", () => {
    expect(toCanvasColor("rgba(1,2,3,0.5)")).toBe("rgba(1, 2, 3, 0.5)");
    expect(toCanvasColor("#a3a7c8")).toBe("#a3a7c8");
    expect(toCanvasColor("transparent")).toBe("transparent");
  });

  it("clamps out-of-range channels", () => {
    expect(toCanvasColor("rgb(300 0 20 / 1.5)")).toBe("rgba(255, 0, 20, 1)");
  });
});
