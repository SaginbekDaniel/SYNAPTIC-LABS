import { describe, expect, it } from "vitest";
import type { InvestigationGraph } from "../../lib/types";
import { DEFAULT_FILTERS, edgeId, edgeStatus, formationMembers, MAX_WORKSPACE_NODES, mergeExpansion, seedPosition, toCanvas } from "./graphModel";

const BIG = "9007199254740993"; // 2^53 + 1

function graph(over: Partial<InvestigationGraph> = {}): InvestigationGraph {
  return {
    snapshot_id: "s1",
    dataset_id: "d1",
    graph_version: "g",
    policy_version: "risk-policy-v2",
    config_sha256: "c".repeat(64),
    input_manifest_sha256: "m".repeat(64),
    computed_at: "2026-11-19T00:00:00Z",
    view_version: "graph-view-v1",
    mode: "overview",
    center: null,
    found: true,
    formations: [
      { id: "f1", kind: "funnel", currency: "KZT", subject_account_id: "hub", account_count: 3, band: "high", priority: 70, temporal_status: "supported", alert_id: "a1" },
      { id: "f2", kind: "chain", currency: "KZT", subject_account_id: "x", account_count: 2, band: "medium", priority: 40, temporal_status: "contradicted", alert_id: null },
    ],
    nodes: [
      { account_id: "hub", hop: null, is_boundary: false, formations: [{ formation_id: "f1", role: "subject" }], band: "high", priority: 70 },
      { account_id: BIG, hop: null, is_boundary: false, formations: [{ formation_id: "f1", role: "entry" }, { formation_id: "f2", role: "member" }], band: "high", priority: 70 },
      { account_id: "x", hop: null, is_boundary: true, formations: [{ formation_id: "f2", role: "subject" }], band: "medium", priority: 40 },
      { account_id: "lone", hop: null, is_boundary: false, formations: [], band: null, priority: null },
    ],
    edges: [
      { kind: "observed_transfer", sender: BIG, receiver: "hub", currency: "KZT", amount_minor: "90071992547409930", n_transactions: 2, first_date: "2026-07-01", last_date: "2026-07-02", evidence_formation_ids: ["f1"], temporal_statuses: ["supported"] },
      { kind: "observed_transfer", sender: "x", receiver: BIG, currency: "USD", amount_minor: "5", n_transactions: 1, first_date: "2026-07-01", last_date: "2026-07-01", evidence_formation_ids: ["f1", "f2"], temporal_statuses: ["contradicted", "supported"] },
      { kind: "observed_transfer", sender: "lone", receiver: "hub", currency: "KZT", amount_minor: "100", n_transactions: 1, first_date: "2026-07-03", last_date: "2026-07-03", evidence_formation_ids: [], temporal_statuses: [] },
    ],
    limits: { max_nodes: 200, max_edges: 1500, max_formations: 25, formations_total: 2, truncated: false, reasons: [] },
    ...over,
  };
}

describe("graph model", () => {
  it("seed positions are deterministic, distinct and independent of input order", () => {
    expect(seedPosition("acc-1")).toEqual(seedPosition("acc-1"));
    const ids = Array.from({ length: 500 }, (_, i) => `acc-${i}`);
    const keys = new Set(ids.map((id) => JSON.stringify(seedPosition(id))));
    expect(keys.size).toBe(ids.length); // no coincident nodes → cose never falls back to Math.random
    const g = graph();
    const shuffled = graph({ nodes: [...g.nodes].reverse() });
    const pos = (m: ReturnType<typeof toCanvas>) => Object.fromEntries(m.nodes.map((n) => [n.id, n.position]));
    expect(pos(toCanvas(shuffled, DEFAULT_FILTERS))).toEqual(pos(toCanvas(g, DEFAULT_FILTERS)));
  });

  it("edge ids cannot collide even when account ids contain separators", () => {
    const a = edgeId({ sender: "a:b", receiver: "c", currency: "KZT" });
    const b = edgeId({ sender: "a", receiver: "b:c", currency: "KZT" });
    expect(a).not.toBe(b);
  });

  it("copies server risk and status; ids and amounts stay exact strings", () => {
    const m = toCanvas(graph(), DEFAULT_FILTERS);
    const big = m.nodes.find((n) => n.id === BIG)!;
    expect(big.band).toBe("high");
    expect(m.nodes.find((n) => n.id === "lone")!).toMatchObject({ band: null, role: "context" });
    expect(m.nodes.find((n) => n.id === "x")!.role).toBe("boundary");
    expect(m.nodes.find((n) => n.id === "hub")!.hub).toBe(true);
    const e = m.edges.find((x) => x.source === BIG)!;
    expect(e.amountMinor).toBe("90071992547409930");
    expect(e.status).toBe("supported");
    expect(m.edges.find((x) => x.source === "x")!.status).toBe("mixed"); // formations disagree: no single claim
    expect(m.edges.find((x) => x.source === "lone")!).toMatchObject({ status: null, evidence: false });
    // Keyboard order = triage order: band, then priority, then id ("9…" sorts before "hub").
    expect(m.order).toEqual([BIG, "hub", "x", "lone"]);
  });

  it("filters hide drawn edges only — formations, nodes and evidence are untouched", () => {
    const g = graph();
    const evidenceOnly = toCanvas(g, { ...DEFAULT_FILTERS, edgeScope: "evidence" });
    expect(evidenceOnly.edges.map((e) => e.source).sort()).toEqual([BIG, "x"].sort());
    expect(evidenceOnly.hiddenEdges).toBe(1);
    expect(evidenceOnly.nodes).toHaveLength(4);
    const contradicted = toCanvas(g, { ...DEFAULT_FILTERS, temporal: ["contradicted"] });
    expect(contradicted.edges.map((e) => e.source).sort()).toEqual(["lone", "x"]); // context edges are not temporal claims
    const usd = toCanvas(g, { ...DEFAULT_FILTERS, currency: "USD" });
    expect(usd.edges.map((e) => e.currency)).toEqual(["USD"]);
    expect(usd.currencies).toEqual(["KZT", "USD"]);
    expect(g.edges).toHaveLength(3); // the DTO itself is never mutated
  });

  it("edge status: none, single, or 'mixed'", () => {
    expect(edgeStatus({ temporal_statuses: [] })).toBeNull();
    expect(edgeStatus({ temporal_statuses: ["possible_ambiguous"] })).toBe("possible_ambiguous");
    expect(edgeStatus({ temporal_statuses: ["supported", "contradicted"] })).toBe("mixed");
  });

  it("merges an expansion from the same snapshot, unioning formations without duplicating edges", () => {
    const cur = graph();
    const next = graph({
      mode: "local",
      center: "hub",
      nodes: [
        { account_id: "hub", hop: 0, is_boundary: false, formations: [{ formation_id: "f3", role: "member" }], band: "low", priority: 5 },
        { account_id: "new", hop: 1, is_boundary: false, formations: [], band: null, priority: null },
      ],
      edges: [
        cur.edges[0]!,
        { kind: "observed_transfer", sender: "hub", receiver: "new", currency: "KZT", amount_minor: "7", n_transactions: 1, first_date: "2026-07-04", last_date: "2026-07-04", evidence_formation_ids: [], temporal_statuses: [] },
      ],
      formations: [{ id: "f3", kind: "fan_out", currency: "KZT", subject_account_id: "hub", account_count: 6, band: "low", priority: 5, temporal_status: null, alert_id: null }],
    });
    const r = mergeExpansion(cur, next);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.graph.nodes.map((n) => n.account_id)).toContain("new");
    expect(r.graph.edges).toHaveLength(4);
    const hub = r.graph.nodes.find((n) => n.account_id === "hub")!;
    expect(hub.formations.map((f) => f.formation_id).sort()).toEqual(["f1", "f3"]);
    expect(hub.band).toBe("high"); // the stored band of the original view is not overwritten
    expect(r.graph.formations.map((f) => f.id)).toEqual(["f1", "f2", "f3"]);
  });

  it("refuses to splice two snapshots or exceed the workspace cap", () => {
    expect(mergeExpansion(graph(), graph({ snapshot_id: "s2" }))).toEqual({ ok: false, reason: "snapshot_changed" });
    expect(mergeExpansion(graph(), graph({ config_sha256: "d".repeat(64) }))).toEqual({ ok: false, reason: "snapshot_changed" });
    const many = graph({
      nodes: Array.from({ length: MAX_WORKSPACE_NODES }, (_, i) => ({ account_id: `n${i}`, hop: 1, is_boundary: false, formations: [], band: null, priority: null })),
    });
    expect(mergeExpansion(graph(), many)).toEqual({ ok: false, reason: "budget" });
  });

  it("formationMembers selects a cluster", () => {
    expect([...formationMembers(graph(), "f2")].sort()).toEqual([BIG, "x"].sort());
  });
});
