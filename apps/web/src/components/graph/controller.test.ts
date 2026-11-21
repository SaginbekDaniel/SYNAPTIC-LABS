import { describe, expect, it, vi } from "vitest";
import { GRAPH_COMMAND_TYPES, GraphController, type GraphViewport, type Point } from "./controller";

/** A faithful little viewport: model coords, pan and zoom, rendered = model * zoom + pan. */
function fakeViewport(nodes: Record<string, Point>) {
  const model = new Map(Object.entries(nodes).map(([k, v]) => [k, { ...v }]));
  let zoom = 1;
  let pan = { x: 0, y: 0 };
  const toRendered = (p: Point) => ({ x: p.x * zoom + pan.x, y: p.y * zoom + pan.y });
  const toModel = (p: Point) => ({ x: (p.x - pan.x) / zoom, y: (p.y - pan.y) / zoom });
  const vp: GraphViewport & { state: () => { zoom: number; pan: Point } } = {
    size: () => ({ width: 800, height: 600 }),
    zoom: () => zoom,
    zoomTo: (level, anchor) => {
      const m = toModel(anchor);
      zoom = level;
      pan = { x: anchor.x - m.x * zoom, y: anchor.y - m.y * zoom };
    },
    panBy: (d) => {
      pan = { x: pan.x + d.x, y: pan.y + d.y };
    },
    fit: () => {
      zoom = 1;
      pan = { x: 0, y: 0 };
    },
    nodePosition: (id) => (model.has(id) ? toRendered(model.get(id)!) : null),
    moveNode: (id, r) => model.set(id, toModel(r)),
    modelPosition: (id) => (model.has(id) ? { ...model.get(id)! } : null),
    setModelPosition: (id, p) => model.set(id, { ...p }),
    nodeIds: () => [...model.keys()],
    centerOn: (id) => {
      const r = toRendered(model.get(id)!);
      pan = { x: pan.x + 400 - r.x, y: pan.y + 300 - r.y };
    },
    state: () => ({ zoom, pan }),
  };
  return vp;
}

describe("GraphController", () => {
  it("exposes only viewing and reading commands — nothing that writes", () => {
    expect([...GRAPH_COMMAND_TYPES].sort()).toEqual(
      [
        "cancel",
        "dragEnd",
        "dragMove",
        "dragStart",
        "expandNeighborhood",
        "focusNode",
        "hover",
        "hoverEnd",
        "pan",
        "resetView",
        "selectEdge",
        "selectNode",
        "zoomAt",
        "zoomStep",
      ].sort(),
    );
    for (const forbidden of ["decide", "openCase", "addNote", "escalate", "dismiss", "close", "delete", "submit"]) {
      expect(GRAPH_COMMAND_TYPES.some((t) => t.toLowerCase().includes(forbidden.toLowerCase()))).toBe(false);
    }
  });

  it("bounds pan steps and zoom, and keeps the zoom anchor fixed", () => {
    const vp = fakeViewport({ a: { x: 100, y: 100 } });
    const c = new GraphController(vp, {}, { maxPanStep: 50, minZoom: 0.5, maxZoom: 2, maxZoomStep: 1.5 });
    c.dispatch({ type: "pan", dx: 10_000, dy: -10_000 });
    expect(vp.state().pan).toEqual({ x: 50, y: -50 });

    vp.fit();
    const before = vp.nodePosition("a")!;
    c.dispatch({ type: "zoomAt", factor: 100, x: before.x, y: before.y }); // clamped to ×1.5
    expect(vp.zoom()).toBeCloseTo(1.5);
    expect(vp.nodePosition("a")).toEqual(before); // anchor did not move
    for (let i = 0; i < 10; i++) c.dispatch({ type: "zoomStep", direction: 1 });
    expect(vp.zoom()).toBe(2);
    for (let i = 0; i < 20; i++) c.dispatch({ type: "zoomStep", direction: -1 });
    expect(vp.zoom()).toBe(0.5);
  });

  it("rejects non-finite and malformed input instead of corrupting the view", () => {
    const vp = fakeViewport({ a: { x: 0, y: 0 } });
    const c = new GraphController(vp);
    expect(c.dispatch({ type: "pan", dx: Number.NaN, dy: 1 })).toBe(false);
    expect(c.dispatch({ type: "zoomAt", factor: 0, x: 1, y: 1 })).toBe(false);
    expect(c.dispatch({ type: "zoomAt", factor: Number.POSITIVE_INFINITY, x: 1, y: 1 })).toBe(false);
    expect(vp.state()).toEqual({ zoom: 1, pan: { x: 0, y: 0 } });
  });

  it("selects only existing nodes and reports selection through callbacks", () => {
    const onSelectNode = vi.fn();
    const c = new GraphController(fakeViewport({ a: { x: 0, y: 0 } }), { onSelectNode });
    expect(c.dispatch({ type: "selectNode", id: "missing" })).toBe(false);
    expect(c.dispatch({ type: "selectNode", id: "a" })).toBe(true);
    expect(c.dispatch({ type: "selectNode", id: null })).toBe(true);
    expect(onSelectNode.mock.calls).toEqual([["a"], [null]]);
  });

  it("drags a node without a jump, keeps it on stage, and cancel restores it exactly", () => {
    const vp = fakeViewport({ a: { x: 100, y: 100 }, b: { x: 300, y: 300 } });
    const c = new GraphController(vp);
    expect(c.dispatch({ type: "dragStart", id: "a", x: 110, y: 95 })).toBe(true);
    c.dispatch({ type: "dragMove", x: 210, y: 195 });
    expect(vp.nodePosition("a")).toEqual({ x: 200, y: 200 }); // offset kept: no jump to the pointer
    c.dispatch({ type: "dragMove", x: 5000, y: -5000 });
    expect(vp.nodePosition("a")).toEqual({ x: 800, y: 0 }); // clamped to the stage
    c.dispatch({ type: "pan", dx: 40, dy: 40 }); // the view moves during the drag…
    c.dispatch({ type: "cancel" });
    expect(c.dragging).toBeNull();
    expect(vp.modelPosition("a")).toEqual({ x: 100, y: 100 }); // …the model position is still restored
    expect(vp.modelPosition("b")).toEqual({ x: 300, y: 300 });
  });

  it("commits a drag on dragEnd and ignores moves without an active drag", () => {
    const vp = fakeViewport({ a: { x: 100, y: 100 } });
    const c = new GraphController(vp);
    expect(c.dispatch({ type: "dragMove", x: 1, y: 1 })).toBe(false);
    c.dispatch({ type: "dragStart", id: "a", x: 100, y: 100 });
    c.dispatch({ type: "dragMove", x: 150, y: 120 });
    expect(c.dispatch({ type: "dragEnd" })).toBe(true);
    c.dispatch({ type: "cancel" });
    expect(vp.modelPosition("a")).toEqual({ x: 150, y: 120 });
  });

  it("hover finds the nearest node within the hit radius and is passive", () => {
    const onHover = vi.fn();
    const onSelectNode = vi.fn();
    const c = new GraphController(fakeViewport({ a: { x: 100, y: 100 }, b: { x: 130, y: 100 } }), { onHover, onSelectNode }, { hitRadius: 20 });
    c.dispatch({ type: "hover", x: 112, y: 100 });
    c.dispatch({ type: "hover", x: 125, y: 101 });
    c.dispatch({ type: "hover", x: 125, y: 102 }); // same node: no repeat event
    c.dispatch({ type: "hover", x: 500, y: 500 });
    expect(onHover.mock.calls).toEqual([["a"], ["b"], [null]]);
    expect(onSelectNode).not.toHaveBeenCalled();
  });

  it("expand is a read request for an existing node only", () => {
    const onExpand = vi.fn();
    const c = new GraphController(fakeViewport({ a: { x: 0, y: 0 } }), { onExpand });
    expect(c.dispatch({ type: "expandNeighborhood", id: "nope" })).toBe(false);
    expect(c.dispatch({ type: "expandNeighborhood", id: "a" })).toBe(true);
    expect(onExpand).toHaveBeenCalledWith("a");
  });
});
