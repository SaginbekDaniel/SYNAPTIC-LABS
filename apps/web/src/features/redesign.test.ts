import { describe, expect, it } from "vitest";
import { monotonePath, niceStep } from "../components/charts/useElementWidth";
import type { AlertDetail, AlertSummary, Transaction } from "../lib/types";
import { accountHandle, byQueueOrder, caseTitle } from "./alerts/alertText";
import { stanceOf } from "./investigation/evidence";
import { accountFlows, buildFormationGraph } from "./investigation/formationGraph";

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

describe("overview priority list", () => {
  const alert = (id: string, band: AlertSummary["risk"]["band"], priority: number | null, first_seen = "2026-01-01T00:00:00Z") =>
    ({ id, first_seen, risk: { band, priority } }) as unknown as AlertSummary;
  it("merges open and in-case pages in the API's queue order", () => {
    const merged = [alert("d", "insufficient_evidence", null), alert("c", "high", 40), alert("a", "high", 90), alert("b", "critical", 10), alert("e", "high", null)].sort(byQueueOrder);
    expect(merged.map((a) => a.id)).toEqual(["b", "a", "c", "e", "d"]);
  });
  it("breaks ties by first seen, then id", () => {
    const merged = [alert("z", "high", 50, "2026-01-02T00:00:00Z"), alert("y", "high", 50), alert("x", "high", 50)].sort(byQueueOrder);
    expect(merged.map((a) => a.id)).toEqual(["x", "y", "z"]);
  });
});

describe("formation graph layout", () => {
  const feeders = Array.from({ length: 24 }, (_, i) => `F${String(i).padStart(3, "0")}`);
  const alert = {
    formation: { kind: "funnel", subject_account_id: "HUB", member_ids: ["HUB", ...feeders], entry_ids: feeders, exit_ids: ["OUT"] },
    coverage: { boundary_accounts: [] },
  } as unknown as AlertDetail;
  const tx = (id: string, s: string, r: string) =>
    ({ id, sender_account_id: s, receiver_account_id: r, amount_minor: "100000", currency: "KZT" }) as unknown as Transaction;
  const txs = [...feeders.map((f, i) => tx(`t${i}`, f, "HUB")), tx("out", "HUB", "OUT")];
  const extent = (g: ReturnType<typeof buildFormationGraph>) => {
    const xs = g.nodes.map((n) => n.position!.x);
    const ys = g.nodes.map((n) => n.position!.y);
    return { w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
  };
  const minDistance = (g: ReturnType<typeof buildFormationGraph>) => {
    let min = Infinity;
    for (const a of g.nodes) for (const b of g.nodes) if (a !== b) min = Math.min(min, Math.hypot(a.position!.x - b.position!.x, a.position!.y - b.position!.y));
    return min;
  };

  it("wraps a 24-feeder funnel into columns so it stays landscape with room for labels", () => {
    const g = buildFormationGraph(alert, txs, new Set());
    const { w, h } = extent(g);
    expect(w).toBeGreaterThan(h);
    expect(minDistance(g)).toBeGreaterThanOrEqual(56);
  });
  it("reads top to bottom on portrait stages without changing the graph itself", () => {
    const land = buildFormationGraph(alert, txs, new Set());
    const port = buildFormationGraph(alert, txs, new Set(), { portrait: true });
    const { w, h } = extent(port);
    expect(h).toBeGreaterThan(w);
    expect(minDistance(port)).toBeGreaterThanOrEqual(56);
    expect(port.nodes.map((n) => [n.id, n.role])).toEqual(land.nodes.map((n) => [n.id, n.role]));
    expect(port.edges).toEqual(land.edges);
    const hub = port.nodes.find((n) => n.id === "HUB")!.position!;
    expect(port.nodes.find((n) => n.id === "F000")!.position!.y).toBeLessThan(hub.y);
    expect(port.nodes.find((n) => n.id === "OUT")!.position!.y).toBeGreaterThan(hub.y);
  });
});
