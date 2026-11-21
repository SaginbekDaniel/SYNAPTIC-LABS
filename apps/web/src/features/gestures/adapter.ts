/**
 * GestureAdapter — maps recognised gestures onto GraphController commands.
 *
 * It only knows the controller's viewing commands; it has no access to the API, cases or any other
 * write path. In "navigate" mode a pinch can select but never move a node, so an unsteady hand
 * cannot rearrange the drawing; "arrange" mode enables dragging nodes explicitly.
 */
import type { GraphController } from "../../components/graph/controller";
import type { GestureEvent } from "./recognizer";

export type GestureMode = "navigate" | "arrange";

export interface StageSize {
  width: number;
  height: number;
}

export interface PointerState {
  x: number;
  y: number;
  pose: "open" | "point" | "pinch" | "other";
  target: string | null;
}

export class GestureAdapter {
  private dragging = false;
  mode: GestureMode = "navigate";
  /** Rendered-pixel pan per unit of normalised hand movement. */
  panGain = 1.4;

  constructor(
    private readonly controller: GraphController,
    private readonly stage: () => StageSize,
  ) {}

  private px(x: number, y: number) {
    const { width, height } = this.stage();
    return { x: x * width, y: y * height };
  }

  /** Apply events; returns the pointer to draw (null when the hand is gone). */
  apply(events: GestureEvent[]): PointerState | null | undefined {
    let pointer: PointerState | null | undefined;
    for (const e of events) {
      switch (e.type) {
        case "pointer": {
          const p = this.px(e.x, e.y);
          // Hover is passive: it highlights, it never selects.
          if (!this.dragging) this.controller.dispatch({ type: "hover", x: p.x, y: p.y });
          pointer = { x: e.x, y: e.y, pose: e.pose, target: this.controller.dragging ?? this.controller.nodeAt(p) };
          break;
        }
        case "pointerLost":
          this.controller.dispatch({ type: "hoverEnd" });
          pointer = null;
          break;
        case "pan": {
          const { width, height } = this.stage();
          this.controller.dispatch({ type: "pan", dx: e.dx * width * this.panGain, dy: e.dy * height * this.panGain });
          break;
        }
        case "tap": {
          const id = this.controller.nodeAt(this.px(e.x, e.y));
          if (id) this.controller.dispatch({ type: "selectNode", id });
          break;
        }
        case "dragStart": {
          if (this.mode !== "arrange") break;
          const p = this.px(e.x, e.y);
          const id = this.controller.nodeAt(p);
          this.dragging = id !== null && this.controller.dispatch({ type: "dragStart", id, x: p.x, y: p.y });
          break;
        }
        case "dragMove":
          if (this.dragging) {
            const p = this.px(e.x, e.y);
            this.controller.dispatch({ type: "dragMove", x: p.x, y: p.y });
          }
          break;
        case "dragEnd":
          if (this.dragging) this.controller.dispatch({ type: "dragEnd" });
          this.dragging = false;
          break;
        case "zoom": {
          const p = this.px(e.x, e.y);
          this.controller.dispatch({ type: "zoomAt", factor: e.factor, x: p.x, y: p.y });
          break;
        }
        case "cancel":
          // Uncertain input: undo an in-flight drag, commit nothing.
          this.controller.dispatch({ type: "cancel" });
          this.dragging = false;
          break;
      }
    }
    return pointer;
  }
}
