/**
 * GraphController — the single command pipeline for viewport interaction.
 *
 * Mouse, touch, keyboard and (optionally) camera gestures all end up here as typed, bounded,
 * non-destructive commands. The command set is deliberately closed: it can move the camera, move
 * a node on screen, select, and *request* a neighbourhood expansion (a read). It has no command that
 * writes anything — case decisions, notes and alerts stay behind their own authenticated forms.
 *
 * The controller talks to the renderer through `GraphViewport`, a small port that Cytoscape
 * implements in GraphCanvas and that unit tests implement with a fake.
 */

export interface Point {
  x: number;
  y: number;
}

/** Positions are in *rendered* (screen) pixels relative to the canvas, unless noted. */
export interface GraphViewport {
  size(): { width: number; height: number };
  zoom(): number;
  /** Zoom to `level` keeping the rendered point `anchor` fixed. */
  zoomTo(level: number, anchor: Point): void;
  panBy(delta: Point): void;
  fit(): void;
  /** Rendered position of a node, or null if it does not exist. */
  nodePosition(id: string): Point | null;
  /** Move a node so that it is drawn at `rendered`. */
  moveNode(id: string, rendered: Point): void;
  /** Model (layout) position, independent of pan/zoom — used to undo a cancelled drag exactly. */
  modelPosition(id: string): Point | null;
  setModelPosition(id: string, model: Point): void;
  nodeIds(): string[];
  centerOn(id: string): void;
}

export type GraphCommand =
  | { type: "pan"; dx: number; dy: number }
  | { type: "zoomAt"; factor: number; x: number; y: number }
  | { type: "zoomStep"; direction: 1 | -1 }
  | { type: "resetView" }
  | { type: "focusNode"; id: string }
  | { type: "selectNode"; id: string | null }
  | { type: "selectEdge"; id: string | null }
  | { type: "hover"; x: number; y: number }
  | { type: "hoverEnd" }
  | { type: "dragStart"; id: string; x: number; y: number }
  | { type: "dragMove"; x: number; y: number }
  | { type: "dragEnd" }
  | { type: "cancel" }
  | { type: "expandNeighborhood"; id: string };

export type GraphCommandType = GraphCommand["type"];

/** Every command the controller accepts. Tests pin this list so a write command cannot slip in. */
export const GRAPH_COMMAND_TYPES: readonly GraphCommandType[] = [
  "pan",
  "zoomAt",
  "zoomStep",
  "resetView",
  "focusNode",
  "selectNode",
  "selectEdge",
  "hover",
  "hoverEnd",
  "dragStart",
  "dragMove",
  "dragEnd",
  "cancel",
  "expandNeighborhood",
];

export interface GraphControllerOptions {
  minZoom: number;
  maxZoom: number;
  /** Largest pan applied by one command, in rendered px (gesture jitter cannot fling the view). */
  maxPanStep: number;
  /** Largest zoom change applied by one command (factor, > 1). */
  maxZoomStep: number;
  /** Hit radius for pointer → node lookup, in rendered px. */
  hitRadius: number;
}

export const DEFAULT_CONTROLLER_OPTIONS: GraphControllerOptions = {
  minZoom: 0.15,
  maxZoom: 3,
  maxPanStep: 240,
  maxZoomStep: 1.5,
  hitRadius: 28,
};

export interface GraphControllerEvents {
  onSelectNode?: (id: string | null) => void;
  onSelectEdge?: (id: string | null) => void;
  onHover?: (id: string | null) => void;
  onExpand?: (id: string) => void;
}

interface DragState {
  id: string;
  /** Model position at drag start (rendered positions change when the view pans). */
  origin: Point;
  /** Offset between pointer and node centre at drag start, so the node does not jump. */
  offset: Point;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const finite = (...values: number[]) => values.every((v) => Number.isFinite(v));

export class GraphController {
  private drag: DragState | null = null;
  private hovered: string | null = null;
  private readonly opts: GraphControllerOptions;

  constructor(
    private readonly viewport: GraphViewport,
    private readonly events: GraphControllerEvents = {},
    options: Partial<GraphControllerOptions> = {},
  ) {
    this.opts = { ...DEFAULT_CONTROLLER_OPTIONS, ...options };
  }

  /** Rendered size of the stage (for mapping normalised pointer input). */
  stageSize(): { width: number; height: number } {
    return this.viewport.size();
  }

  get dragging(): string | null {
    return this.drag?.id ?? null;
  }

  get hoveredNode(): string | null {
    return this.hovered;
  }

  /** Nearest node to a rendered point within the hit radius, or null. */
  nodeAt(p: Point, radius = this.opts.hitRadius): string | null {
    let best: string | null = null;
    let bestD = radius * radius;
    for (const id of this.viewport.nodeIds()) {
      const q = this.viewport.nodePosition(id);
      if (!q) continue;
      const d = (q.x - p.x) ** 2 + (q.y - p.y) ** 2;
      if (d <= bestD) {
        bestD = d;
        best = id;
      }
    }
    return best;
  }

  /** Apply one command. Returns false if it was rejected (unknown node, non-finite input, …). */
  dispatch(cmd: GraphCommand): boolean {
    switch (cmd.type) {
      case "pan": {
        if (!finite(cmd.dx, cmd.dy)) return false;
        const m = this.opts.maxPanStep;
        this.viewport.panBy({ x: clamp(cmd.dx, -m, m), y: clamp(cmd.dy, -m, m) });
        return true;
      }
      case "zoomAt": {
        if (!finite(cmd.factor, cmd.x, cmd.y) || cmd.factor <= 0) return false;
        const step = this.opts.maxZoomStep;
        const factor = clamp(cmd.factor, 1 / step, step);
        const level = clamp(this.viewport.zoom() * factor, this.opts.minZoom, this.opts.maxZoom);
        const { width, height } = this.viewport.size();
        this.viewport.zoomTo(level, { x: clamp(cmd.x, 0, width), y: clamp(cmd.y, 0, height) });
        return true;
      }
      case "zoomStep": {
        const { width, height } = this.viewport.size();
        return this.dispatch({ type: "zoomAt", factor: cmd.direction > 0 ? 1.25 : 0.8, x: width / 2, y: height / 2 });
      }
      case "resetView":
        this.cancelDrag();
        this.viewport.fit();
        return true;
      case "focusNode":
        if (!this.viewport.nodePosition(cmd.id)) return false;
        this.viewport.centerOn(cmd.id);
        return true;
      case "selectNode":
        if (cmd.id !== null && !this.viewport.nodePosition(cmd.id)) return false;
        this.events.onSelectNode?.(cmd.id);
        return true;
      case "selectEdge":
        this.events.onSelectEdge?.(cmd.id);
        return true;
      case "hover": {
        if (!finite(cmd.x, cmd.y)) return false;
        const id = this.nodeAt({ x: cmd.x, y: cmd.y });
        if (id !== this.hovered) {
          this.hovered = id;
          this.events.onHover?.(id);
        }
        return true;
      }
      case "hoverEnd":
        if (this.hovered !== null) {
          this.hovered = null;
          this.events.onHover?.(null);
        }
        return true;
      case "dragStart": {
        if (!finite(cmd.x, cmd.y)) return false;
        const pos = this.viewport.nodePosition(cmd.id);
        const model = this.viewport.modelPosition(cmd.id);
        if (!pos || !model) return false;
        this.cancelDrag();
        this.drag = { id: cmd.id, origin: model, offset: { x: pos.x - cmd.x, y: pos.y - cmd.y } };
        return true;
      }
      case "dragMove": {
        if (!this.drag || !finite(cmd.x, cmd.y)) return false;
        const { width, height } = this.viewport.size();
        // A node can be moved anywhere on the stage, never off it.
        this.viewport.moveNode(this.drag.id, {
          x: clamp(cmd.x + this.drag.offset.x, 0, width),
          y: clamp(cmd.y + this.drag.offset.y, 0, height),
        });
        return true;
      }
      case "dragEnd":
        if (!this.drag) return false;
        this.drag = null;
        return true;
      case "cancel":
        this.cancelDrag();
        return this.dispatch({ type: "hoverEnd" });
      case "expandNeighborhood":
        if (!this.viewport.nodePosition(cmd.id)) return false;
        this.events.onExpand?.(cmd.id);
        return true;
    }
  }

  /** Abort an active drag and put the node back where it was. */
  private cancelDrag(): void {
    if (!this.drag) return;
    const { id, origin } = this.drag;
    this.drag = null;
    if (this.viewport.modelPosition(id)) this.viewport.setModelPosition(id, origin);
  }
}
