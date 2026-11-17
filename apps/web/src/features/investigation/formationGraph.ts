import type { GraphEdgeSpec, GraphNodeSpec, NodeRole } from "../../components/graph/GraphCanvas";
import type { AlertDetail, Transaction } from "../../lib/types";

/** Aggregate evidence transactions per ordered pair with exact BigInt sums. */
export function buildFormationGraph(alert: AlertDetail, txs: Transaction[], highlight: ReadonlySet<string>) {
  const f = alert.formation;
  const boundary = new Set(alert.coverage.boundary_accounts);
  const roleOf = (id: string): NodeRole => {
    if (boundary.has(id)) return "boundary";
    if (id === f.subject_account_id) return "subject";
    if (f.entry_ids.includes(id)) return "entry";
    if (f.exit_ids.includes(id)) return "exit";
    return "member";
  };
  const pairs = new Map<string, { source: string; target: string; sum: bigint; count: number; currency: string; hl: boolean }>();
  const nodeIds = new Set<string>([...f.member_ids, ...f.exit_ids]);
  for (const tx of txs) {
    nodeIds.add(tx.sender_account_id);
    nodeIds.add(tx.receiver_account_id);
    const key = `${tx.sender_account_id}\u0000${tx.receiver_account_id}\u0000${tx.currency}`;
    const prev = pairs.get(key);
    const amount = BigInt(tx.amount_minor);
    if (prev) {
      prev.sum += amount;
      prev.count += 1;
      prev.hl ||= highlight.has(tx.id);
    } else {
      pairs.set(key, {
        source: tx.sender_account_id,
        target: tx.receiver_account_id,
        sum: amount,
        count: 1,
        currency: tx.currency,
        hl: highlight.has(tx.id),
      });
    }
  }
  const nodes: GraphNodeSpec[] = [...nodeIds].sort().map((id) => ({ id, role: roleOf(id) }));
  if (f.kind === "funnel") layoutFunnel(nodes, f.subject_account_id, new Set(f.entry_ids), new Set(f.exit_ids));
  // A fan-out reads the same way as a funnel: the source sits centre-left, recipients on the right arc.
  if (f.kind === "fanout") layoutFunnel(nodes, f.subject_account_id, new Set(), new Set(f.exit_ids));
  if (f.kind === "cycle") layoutRing(nodes, f.member_ids);
  const edges: GraphEdgeSpec[] = [...pairs.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([key, p]) => ({
      id: `e:${key}`,
      source: p.source,
      target: p.target,
      amountMinor: p.sum.toString(),
      currency: p.currency,
      count: p.count,
      highlighted: p.hl,
    }));
  const roles = [...new Set(nodes.map((n) => n.role))];
  return { nodes, edges, roles };
}

/**
 * Deterministic flow layout for a funnel: feeders on a left arc, onward recipients on a
 * right arc, centre in the middle — money reads left to right and no edge crosses a node.
 */
function layoutFunnel(nodes: GraphNodeSpec[], center: string, entries: Set<string>, exits: Set<string>): void {
  const left = nodes.filter((n) => entries.has(n.id) && n.id !== center);
  const right = nodes.filter((n) => !entries.has(n.id) && n.id !== center && exits.has(n.id));
  const other = nodes.filter((n) => n.id !== center && !entries.has(n.id) && !exits.has(n.id));
  const place = (group: GraphNodeSpec[], from: number, to: number, radius: number) => {
    group.forEach((n, i) => {
      const a = group.length === 1 ? (from + to) / 2 : from + ((to - from) * i) / (group.length - 1);
      n.position = { x: Math.cos(a) * radius, y: Math.sin(a) * radius };
    });
  };
  const radius = (n: number) => Math.max(160, n * 22);
  const deg = Math.PI / 180;
  place(left, 110 * deg, 250 * deg, radius(left.length));
  place(right, -70 * deg, 70 * deg, radius(right.length));
  place(other, 80 * deg, 100 * deg, radius(other.length) * 1.2);
  const c = nodes.find((n) => n.id === center);
  if (c) c.position = { x: 0, y: 0 };
}

/** Members of a cycle on a ring in cycle order (clockwise), other accounts outside it. */
function layoutRing(nodes: GraphNodeSpec[], ring: readonly string[]): void {
  const radius = Math.max(140, ring.length * 40);
  const index = new Map(ring.map((id, i) => [id, i]));
  const outside = nodes.filter((n) => !index.has(n.id));
  for (const n of nodes) {
    const i = index.get(n.id);
    if (i === undefined) continue;
    const a = -Math.PI / 2 + (2 * Math.PI * i) / ring.length;
    n.position = { x: Math.cos(a) * radius, y: Math.sin(a) * radius };
  }
  outside.forEach((n, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * (i + 0.5)) / Math.max(1, outside.length);
    n.position = { x: Math.cos(a) * radius * 1.8, y: Math.sin(a) * radius * 1.8 };
  });
}
