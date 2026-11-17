import { describe, expect, it } from "vitest";
import { monotonePath, niceStep } from "../components/charts/useElementWidth";
import type { Transaction } from "../lib/types";
import { accountHandle, caseTitle } from "./alerts/alertText";
import { stanceOf } from "./investigation/evidence";
import { accountFlows } from "./investigation/formationGraph";

describe("chart helpers", () => {
  it("picks round tick steps for count axes", () => {
    expect(niceStep(23)).toBe(10);
    expect(niceStep(7)).toBe(2);
    expect(niceStep(1)).toBe(1);
    expect(niceStep(380)).toBe(100);
  });
  it("smooths without overshooting below zero", () => {
    const d = monotonePath([
      [0, 100],
      [10, 0],
      [20, 0],
      [30, 100],
    ]);
    // y grows downward in SVG: a dip below the baseline would mean a control point beyond y=100.
    const ys = [...d.matchAll(/-?\d+(?:\.\d+)?,(-?\d+(?:\.\d+)?)/g)].map((m) => Number(m[1]));
    expect(Math.max(...ys)).toBeLessThanOrEqual(100);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
  });
});

describe("investigation semantics", () => {
  it("places band caps among weakening findings and coverage facts among unknowns", () => {
    expect(stanceOf("STRUCT_FUNNEL_FEEDERS")).toBe("supports");
    expect(stanceOf("TEMPORAL_CONTRADICTED")).toBe("weakens");
    expect(stanceOf("BAND_CAPPED_BY_EVIDENCE")).toBe("weakens");
    expect(stanceOf("COVERAGE_DAY_PRECISION")).toBe("unknown");
  });
  it("sums account flows exactly beyond 2^53", () => {
    const tx = (id: string, from: string, to: string, amount: string): Transaction =>
      ({ id, sender_account_id: from, receiver_account_id: to, amount_minor: amount, currency: "KZT" }) as Transaction;
    const f = accountFlows("C", [tx("1", "A", "C", "9007199254740993"), tx("2", "B", "C", "1"), tx("3", "C", "D", "5")]);
    expect(f.inSum).toBe(9007199254740994n);
    expect(f.outSum).toBe(5n);
    expect([f.inCount, f.outCount, f.related.length, f.mixedCurrency]).toEqual([2, 1, 3, false]);
  });
});

describe("readable titles keep exact ids available", () => {
  it("renders stored case titles like alert titles", () => {
    const c = caseTitle("funnel:6300477387530");
    expect(c.account).toBe("6300477387530");
    expect(c.title).toBe("Воронка сбора средств ··7530");
    expect(caseTitle("alert:x").title).toBe("alert x"); // unknown kind falls back to the raw value
    expect(caseTitle("free text").account).toBeNull();
  });
  it("never shortens short ids", () => {
    expect(accountHandle("A1")).toBe("A1");
  });
});
