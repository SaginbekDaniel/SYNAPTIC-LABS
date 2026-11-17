import { describe, expect, it } from "vitest";
import { formatBp, formatDate, formatEventTime, formatMoney, formatRatio, sumMinor } from "./format";

describe("money", () => {
  it("formats integer minor units exactly, beyond 2^53", () => {
    // 90 071 992 547 409 93 tiyn: not representable as a JS number.
    expect(formatMoney("9007199254740993")).toBe("90 071 992 547 409,93 ₸");
  });
  it("omits zero fraction by default", () => {
    expect(formatMoney("12500000")).toBe("125 000 ₸");
  });
  it("sums without float drift", () => {
    expect(sumMinor(["10", "20", "9007199254740993"])).toBe(9007199254741023n);
  });
  it("rejects non-integer strings", () => {
    expect(() => formatMoney("1.5")).toThrow();
  });
});

describe("time", () => {
  it("day-precision records never show a clock time", () => {
    expect(formatEventTime("2026-07-08", null)).toBe("08.07.2026");
  });
  it("calendar dates do not shift with local timezone", () => {
    expect(formatDate("2026-01-01")).toBe("01.01.2026");
  });
  it("basis points", () => {
    expect(formatBp(9350)).toBe("93,5 %");
  });
});

describe("formatRatio", () => {
  it("keeps undefined metrics visible instead of showing 0 %", () => {
    expect(formatRatio(null)).toBe("н/д");
    expect(formatRatio(undefined)).toBe("н/д");
  });
  it("formats ratios as percentages", () => {
    expect(formatRatio(0.5632).replace(/\s/g, " ")).toBe("56,3 %");
    expect(formatRatio(1, 0).replace(/\s/g, " ")).toBe("100 %");
  });
});
