import type { GraphEdgeSpec, GraphNodeSpec, NodeRole } from "../../components/graph/GraphCanvas";
import type { AlertDetail, Transaction } from "../../lib/types";

export interface FormationGraph {
  nodes: GraphNodeSpec[];
  edges: GraphEdgeSpec[];
  roles: NodeRole[];
}

/**
 * Aggregate evidence transactions per ordered pair with exact BigInt sums, and place every node
 * with a deterministic layout chosen by formation kind — money always reads left to right
 * (or clockwise for a loop), and the same alert always looks the same.
 */
export function buildFormationGraph(alert: AlertDetail, txs: Transaction[], highlight: ReadonlySet<string>): FormationGraph {
  const f = alert.formation;
  const boundary = new Set(alert.coverage.boundary_accounts);
  const roleOf = (id: string): NodeRole => {
    if (boundary.has(id)) return "boundary";
    if (id === f.subject_account_id) return "subject";
    if (f.entry_ids.includes(id)) return "entry";
    if (f.exit_ids.includes(id)) return "exit";
    return "member";
  };
  const pairs = new Map<string, { source: string; target: string; sum: bigint; count: number; currency: string; hl: boolean; txIds: string[] }>();
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
      prev.txIds.push(tx.id);
    } else {
      pairs.set(key, {
        source: tx.sender_account_id,
        target: tx.receiver_account_id,
        sum: amount,
        count: 1,
        currency: tx.currency,
        hl: highlight.has(tx.id),
        txIds: [tx.id],
      });
    }
  }
  const nodes: GraphNodeSpec[] = [...nodeIds].sort().map((id) => ({ id, role: roleOf(id) }));
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
      txIds: p.txIds,
    }));

  if (f.kind === "cycle") layoutCycle(nodes, f.member_ids);
  else if (f.kind === "chain") layoutChain(nodes, f.member_ids, edges);
  else layoutFlow(nodes, f.subject_account_id, new Set(f.entry_ids), new Set(f.exit_ids));

  const roles = [...new Set(nodes.map((n) => n.role))];
  return { nodes, edges, roles };
}

/** Spread `count` items over a vertical span centred on 0, or an arc when there are many. */
function column(group: GraphNodeSpec[], x: number, gap: number, bend: number): void {
  const n = group.length;
  group.forEach((node, i) => {
    const y = (i - (n - 1) / 2) * gap;
    // Large groups bow outward slightly so edges into the hub fan instead of overlapping.
    const t = n > 1 ? (i - (n - 1) / 2) / ((n - 1) / 2) : 0;
    node.position = { x: x + bend * t * t, y };
  });
}

/**
 * Funnel and fan-out: sources in a left column, the hub in the centre, recipients to the right,
 * anything further downstream in a fourth column.
 */
function layoutFlow(nodes: GraphNodeSpec[], center: string, entries: Set<string>, exits: Set<string>): void {
  const left = nodes.filter((n) => n.id !== center && entries.has(n.id));
  const right = nodes.filter((n) => n.id !== center && !entries.has(n.id) && exits.has(n.id));
  const other = nodes.filter((n) => n.id !== center && !entries.has(n.id) && !exits.has(n.id));
  const gap = (n: number) => (n > 12 ? 40 : n > 6 ? 52 : 70);
  column(left, -260, gap(left.length), left.length > 6 ? -60 : 0);
  column(right, 260, gap(right.length), right.length > 6 ? 60 : 0);
  column(other, 480, gap(other.length), 0);
  const c = nodes.find((n) => n.id === center);
  if (c) c.position = { x: 0, y: 0 };
}

/** Chain: the path in hop order along a straight line; side accounts (if any) below their neighbour. */
function layoutChain(nodes: GraphNodeSpec[], path: readonly string[], edges: GraphEdgeSpec[]): void {
  const step = 190;
  const order = new Map(path.map((id, i) => [id, i]));
  for (const n of nodes) {
    const i = order.get(n.id);
    if (i !== undefined) n.position = { x: (i - (path.length - 1) / 2) * step, y: 0 };
  }
  const placedBelow = new Map<number, number>();
  for (const n of nodes) {
    if (n.position) continue;
    const e = edges.find((x) => x.source === n.id || x.target === n.id);
    const other = e ? (e.source === n.id ? e.target : e.source) : undefined;
    const idx = other !== undefined ? (order.get(other) ?? 0) : 0;
    const k = (placedBelow.get(idx) ?? 0) + 1;
    placedBelow.set(idx, k);
    n.position = { x: (idx - (path.length - 1) / 2) * step, y: 110 * k };
  }
}

/** Loop members on a circle in observed order (clockwise from the top), other accounts outside. */
function layoutCycle(nodes: GraphNodeSpec[], loop: readonly string[]): void {
  const order = new Map(loop.map((id, i) => [id, i]));
  const radius = Math.max(140, loop.length * 45);
  const outside = nodes.filter((n) => !order.has(n.id));
  for (const n of nodes) {
    const i = order.get(n.id);
    if (i === undefined) continue;
    const a = -Math.PI / 2 + (2 * Math.PI * i) / loop.length;
    n.position = { x: Math.cos(a) * radius, y: Math.sin(a) * radius };
  }
  outside.forEach((n, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * (i + 0.5)) / Math.max(1, outside.length);
    n.position = { x: Math.cos(a) * radius * 1.8, y: Math.sin(a) * radius * 1.8 };
  });
}

/** Per-account flows inside the formation evidence (exact BigInt), for the selection panel. */
export function accountFlows(id: string, txs: Transaction[]) {
  let inSum = 0n;
  let outSum = 0n;
  let inCount = 0;
  let outCount = 0;
  const currencies = new Set<string>();
  const related: Transaction[] = [];
  for (const tx of txs) {
    if (tx.receiver_account_id === id) {
      inSum += BigInt(tx.amount_minor);
      inCount += 1;
    }
    if (tx.sender_account_id === id) {
      outSum += BigInt(tx.amount_minor);
      outCount += 1;
    }
    if (tx.receiver_account_id === id || tx.sender_account_id === id) {
      related.push(tx);
      currencies.add(tx.currency);
    }
  }
  return { inSum, outSum, inCount, outCount, related, mixedCurrency: currencies.size > 1 };
}
