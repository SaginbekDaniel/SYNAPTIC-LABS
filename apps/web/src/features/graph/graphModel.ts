/**
 * Pure transforms between the graph-view-v1 DTO and the canvas. No scoring happens here: band,
 * priority and temporal status are copied from the server; filters only hide what is drawn.
 */
import type { EdgeStatus, GraphEdgeSpec, GraphNodeSpec } from "../../components/graph/GraphCanvas";
import type { Band, InvestigationEdge, InvestigationGraph, TemporalStatus } from "../../lib/types";

export const BAND_ORDER: readonly Band[] = ["critical", "high", "medium", "insufficient_evidence", "low"];
const BAND_RANK: Record<string, number> = Object.fromEntries(BAND_ORDER.map((b, i) => [b, i]));

/** Hard cap on what one workspace session accumulates through expansions. */
export const MAX_WORKSPACE_NODES = 400;

export type EdgeScope = "all" | "evidence";

export interface ClientFilters {
  edgeScope: EdgeScope;
  /** Temporal statuses to keep among evidence edges; empty = all. Context edges are unaffected. */
  temporal: TemporalStatus[];
  /** Currency to keep; null = all. */
  currency: string | null;
}

export const DEFAULT_FILTERS: ClientFilters = { edgeScope: "all", temporal: [], currency: null };

/**
 * Edge ids must be unambiguous for any account id (ids may contain ":" or spaces), so the parts are
 * JSON-encoded rather than joined with a separator.
 */
export function edgeId(e: Pick<InvestigationEdge, "sender" | "receiver" | "currency">): string {
  return `e:${JSON.stringify([e.sender, e.receiver, e.currency])}`;
}

/** One status for drawing: the formations' common status, "mixed" if they disagree, null if none. */
export function edgeStatus(e: Pick<InvestigationEdge, "temporal_statuses">): EdgeStatus | null {
  if (e.temporal_statuses.length === 0) return null;
  const [only] = e.temporal_statuses;
  return e.temporal_statuses.length === 1 && only ? only : "mixed";
}

/** FNV-1a 32-bit — stable across browsers, used only to seed layout positions. */
export function hash32(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/**
 * Deterministic, distinct starting position per account. Cytoscape's force layout only falls back
 * to Math.random() when two nodes coincide; distinct seeds make the layout a pure function of the
 * graph, so the same snapshot draws the same picture on every reload.
 */
export function seedPosition(id: string): { x: number; y: number } {
  const h = hash32(id);
  const angle = ((h & 0xffff) / 0x10000) * 2 * Math.PI;
  const radius = 80 + ((h >>> 16) / 0x10000) * 320;
  return { x: Math.round(Math.cos(angle) * radius * 1000) / 1000, y: Math.round(Math.sin(angle) * radius * 1000) / 1000 };
}

export function compareByPriority(a: { band: Band | null; priority: number | null; id: string }, b: typeof a): number {
  const ra = (a.band && BAND_RANK[a.band]) ?? 9;
  const rb = (b.band && BAND_RANK[b.band]) ?? 9;
  if (ra !== rb) return ra - rb;
  const pa = a.priority ?? -1;
  const pb = b.priority ?? -1;
  if (pa !== pb) return pb - pa;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

export interface CanvasModel {
  nodes: GraphNodeSpec[];
  edges: GraphEdgeSpec[];
  hiddenEdges: number;
  currencies: string[];
  /** Node ids in triage order (keyboard navigation follows it). */
  order: string[];
}

export function toCanvas(g: InvestigationGraph, filters: ClientFilters): CanvasModel {
  const subjects = new Set(g.formations.map((f) => f.subject_account_id));
  const nodes: GraphNodeSpec[] = g.nodes.map((n) => ({
    id: n.account_id,
    role: n.is_boundary ? "boundary" : g.center === n.account_id ? "subject" : n.formations.length ? "member" : "context",
    band: n.band ?? null,
    hub: subjects.has(n.account_id),
    position: seedPosition(n.account_id),
  }));
  const currencies = [...new Set(g.edges.map((e) => e.currency))].sort();
  let hidden = 0;
  const edges: GraphEdgeSpec[] = [];
  for (const e of g.edges) {
    const status = edgeStatus(e);
    const evidence = e.evidence_formation_ids.length > 0;
    const keep =
      (filters.edgeScope === "all" || evidence) &&
      (filters.currency === null || e.currency === filters.currency) &&
      (!evidence || filters.temporal.length === 0 || e.temporal_statuses.some((s) => filters.temporal.includes(s)));
    if (!keep) {
      hidden++;
      continue;
    }
    edges.push({
      id: edgeId(e),
      source: e.sender,
      target: e.receiver,
      amountMinor: e.amount_minor,
      currency: e.currency,
      count: e.n_transactions,
      evidence,
      status,
    });
  }
  const order = [...g.nodes]
    .map((n) => ({ id: n.account_id, band: n.band ?? null, priority: n.priority ?? null }))
    .sort(compareByPriority)
    .map((n) => n.id);
  return { nodes, edges, hiddenEdges: hidden, currencies, order };
}

export type MergeResult = { ok: true; graph: InvestigationGraph } | { ok: false; reason: "snapshot_changed" | "budget" };

/**
 * Merge a local expansion into the current workspace. Refuses data from another snapshot (the
 * analyst would otherwise see two analyses spliced together) and growth past the workspace cap.
 */
export function mergeExpansion(current: InvestigationGraph, next: InvestigationGraph): MergeResult {
  if (current.snapshot_id !== next.snapshot_id || current.config_sha256 !== next.config_sha256) {
    return { ok: false, reason: "snapshot_changed" };
  }
  const nodes = new Map(current.nodes.map((n) => [n.account_id, n]));
  for (const n of next.nodes) {
    const prev = nodes.get(n.account_id);
    if (!prev) {
      nodes.set(n.account_id, n);
      continue;
    }
    const refs = new Map(prev.formations.map((r) => [r.formation_id, r]));
    for (const r of n.formations) refs.set(r.formation_id, r);
    nodes.set(n.account_id, {
      ...prev,
      formations: [...refs.values()],
      // Hop stays relative to the workspace's original centre.
      hop: prev.hop ?? n.hop,
    });
  }
  if (nodes.size > MAX_WORKSPACE_NODES) return { ok: false, reason: "budget" };
  const edges = new Map(current.edges.map((e) => [edgeId(e), e]));
  for (const e of next.edges) if (!edges.has(edgeId(e))) edges.set(edgeId(e), e);
  const formations = new Map(current.formations.map((f) => [f.id, f]));
  for (const f of next.formations) formations.set(f.id, f);
  return {
    ok: true,
    graph: {
      ...current,
      nodes: [...nodes.values()],
      edges: [...edges.values()],
      formations: [...formations.values()].sort((a, b) =>
        compareByPriority({ band: a.band, priority: a.priority ?? null, id: a.id }, { band: b.band, priority: b.priority ?? null, id: b.id }),
      ),
      limits: { ...current.limits, truncated: current.limits.truncated || next.limits.truncated, reasons: [...new Set([...current.limits.reasons, ...next.limits.reasons])] },
    },
  };
}

/** Accounts belonging to one formation, for highlighting a cluster. */
export function formationMembers(g: InvestigationGraph, formationId: string): Set<string> {
  return new Set(g.nodes.filter((n) => n.formations.some((r) => r.formation_id === formationId)).map((n) => n.account_id));
}
