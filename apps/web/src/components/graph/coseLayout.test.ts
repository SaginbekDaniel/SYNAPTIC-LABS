import { afterEach, describe, expect, it, vi } from "vitest";
import { seedPosition } from "../../features/graph/graphModel";
import { computeCoseLayout, layoutKey, type LayoutInput } from "./coseLayout";

function input(n = 40): LayoutInput {
  const nodes = Array.from({ length: n }, (_, i) => ({ id: `acc-${i}`, ...seedPosition(`acc-${i}`), w: i % 7 === 0 ? 36 : 24, h: i % 7 === 0 ? 36 : 24 }));
  const edges = Array.from({ length: n - 1 }, (_, i) => ({ source: `acc-${i + 1}`, target: `acc-${Math.floor(i / 3)}` }));
  return { nodes, edges };
}

describe("computeCoseLayout", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is deterministic and never needs Math.random (seeds are kept, so no node starts coincident)", () => {
    const random = vi.spyOn(Math, "random");
    const a = computeCoseLayout(input());
    const b = computeCoseLayout(input());
    expect(Array.from(a)).toEqual(Array.from(b));
    expect(random).not.toHaveBeenCalled();
  });

  it("returns finite, distinct positions in node order, and edges to unknown nodes are ignored", () => {
    const base = input(20);
    const withStray = { ...base, edges: [...base.edges, { source: "acc-1", target: "missing" }] };
    const p = computeCoseLayout(withStray);
    expect(p).toHaveLength(40);
    expect(Array.from(p).every(Number.isFinite)).toBe(true);
    const points = new Set(Array.from({ length: 20 }, (_, i) => `${p[2 * i]!.toFixed(3)},${p[2 * i + 1]!.toFixed(3)}`));
    expect(points.size).toBe(20);
    expect(Array.from(computeCoseLayout(base))).toEqual(Array.from(p));
  });

  it("the start positions matter: different seeds give a different picture", () => {
    const base = input(20);
    const moved = { ...base, nodes: base.nodes.map((n, i) => (i === 0 ? { ...n, x: n.x + 200 } : n)) };
    expect(Array.from(computeCoseLayout(moved))).not.toEqual(Array.from(computeCoseLayout(base)));
  });
});

describe("layoutKey", () => {
  it("changes with any input that changes the result, and only then", () => {
    const base = input(10);
    const key = layoutKey(base);
    expect(layoutKey(input(10))).toBe(key);
    const variants: LayoutInput[] = [
      { ...base, nodes: base.nodes.map((n, i) => (i === 3 ? { ...n, w: n.w + 1 } : n)) },
      { ...base, nodes: base.nodes.map((n, i) => (i === 3 ? { ...n, x: n.x + 0.001 } : n)) },
      { ...base, nodes: [...base.nodes].reverse() },
      { ...base, edges: base.edges.slice(1) },
      { ...base, edges: base.edges.map((e, i) => (i === 0 ? { source: e.target, target: e.source } : e)) },
    ];
    for (const v of variants) expect(layoutKey(v)).not.toBe(key);
  });

  it("ids cannot be crafted to collide through separators", () => {
    const a: LayoutInput = { nodes: [{ id: "a:1", x: 0, y: 0, w: 1, h: 1 }], edges: [] };
    const b: LayoutInput = { nodes: [{ id: "a", x: 0, y: 0, w: 1, h: 1 }], edges: [] };
    expect(layoutKey(a)).not.toBe(layoutKey(b));
    const c: LayoutInput = { nodes: [{ id: "x", x: 1, y: 23, w: 1, h: 1 }], edges: [] };
    const d: LayoutInput = { nodes: [{ id: "x", x: 12, y: 3, w: 1, h: 1 }], edges: [] };
    expect(layoutKey(c)).not.toBe(layoutKey(d));
  });
});
