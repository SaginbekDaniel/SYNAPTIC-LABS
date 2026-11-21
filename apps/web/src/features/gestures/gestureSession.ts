/**
 * GestureSession — orchestrates CameraSession → HandLandmarkEngine → GestureRecognizer →
 * GestureAdapter → GraphController, and owns their lifecycle.
 *
 * It is an external store (subscribe/getSnapshot) so the ~30 Hz pointer updates re-render only the
 * pointer layer, not the graph page. Every exit path — explicit stop, Escape, hidden tab, unmount,
 * camera loss, engine failure — goes through stop(), which cancels the active gesture, stops the
 * camera tracks and disposes the worker. A later start is always a new, deliberate click.
 */
import type { GraphController } from "../../components/graph/controller";
import { GestureAdapter, type GestureMode, type PointerState } from "./adapter";
import { CameraSession, type CameraState } from "./cameraSession";
import { HandLandmarkEngine } from "./landmarkEngine";
import { GestureRecognizer, type Phase, type Tracking } from "./recognizer";

export type GestureUi = "off" | "consent" | "starting" | "loading" | "calibrating" | "active" | "failed";
export type GestureFailure = Exclude<CameraState, "off" | "requesting" | "live"> | "engine" | "hidden";

export interface GestureSnapshot {
  ui: GestureUi;
  failure: GestureFailure | null;
  tracking: Tracking;
  phase: Phase;
  pointer: PointerState | null;
  mode: GestureMode;
  dominant: "Left" | "Right";
}

const FRAME_INTERVAL_MS = 33; // ≤ 30 inferences per second
const CALIBRATION_MS = 500;

export class GestureSession {
  private snap: GestureSnapshot = { ui: "off", failure: null, tracking: "searching", phase: "idle", pointer: null, mode: "navigate", dominant: "Right" };
  private readonly listeners = new Set<() => void>();
  private camera: CameraSession | null = null;
  private engine: HandLandmarkEngine | null = null;
  private recognizer: GestureRecognizer | null = null;
  private adapter: GestureAdapter | null = null;
  private controller: GraphController | null = null;
  private video: HTMLVideoElement | null = null;
  private generation = 0;
  private running = false;
  private lastFrame = 0;
  private trackedSince: number | null = null;

  subscribe = (l: () => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };
  getSnapshot = () => this.snap;

  private patch(p: Partial<GestureSnapshot>): void {
    this.snap = { ...this.snap, ...p };
    this.listeners.forEach((l) => l());
  }

  attachVideo(video: HTMLVideoElement | null): void {
    this.video = video;
  }

  setController(controller: GraphController | null): void {
    if (controller === this.controller) return;
    // The graph was rebuilt (filter, expansion): drop whatever gesture was bound to the old drawing.
    this.recognizer?.stop();
    this.controller = controller;
    this.adapter = controller ? new GestureAdapter(controller, () => controller.stageSize()) : null;
    if (this.adapter) this.adapter.mode = this.snap.mode;
    if (!controller && this.snap.ui !== "off" && this.snap.ui !== "consent") this.stop();
  }

  setMode(mode: GestureMode): void {
    if (this.adapter) this.adapter.mode = mode;
    this.patch({ mode });
  }

  setDominant(hand: "Left" | "Right"): void {
    this.recognizer?.setDominant(hand);
    this.patch({ dominant: hand });
  }

  /** First click: explain before asking the browser for the camera. */
  requestConsent(): void {
    if (this.snap.ui === "off" || this.snap.ui === "failed") this.patch({ ui: "consent", failure: null });
  }

  dismissConsent(): void {
    if (this.snap.ui === "consent") this.patch({ ui: "off" });
  }

  /** Second, deliberate click: start the camera and the local recogniser. */
  async start(): Promise<void> {
    if (this.snap.ui !== "consent" || !this.video || !this.controller) return;
    const gen = ++this.generation;
    this.patch({ ui: "starting", failure: null, tracking: "searching", phase: "idle", pointer: null });
    const camera = new CameraSession({ isSecureContext: window.isSecureContext, mediaDevices: navigator.mediaDevices });
    this.camera = camera;
    camera.onChange((state) => {
      if (gen === this.generation && state === "ended") this.fail("ended");
    });
    const state = await camera.start(this.video);
    if (gen !== this.generation) return;
    if (state !== "live") {
      this.fail(state === "off" || state === "requesting" ? "error" : state);
      return;
    }
    this.patch({ ui: "loading" });
    const engine = new HandLandmarkEngine();
    this.engine = engine;
    try {
      await engine.start(() => {
        if (gen === this.generation) this.fail("engine");
      });
    } catch {
      if (gen === this.generation) this.fail("engine");
      else engine.dispose();
      return;
    }
    if (gen !== this.generation) {
      engine.dispose();
      return;
    }
    this.recognizer = new GestureRecognizer({ dominant: this.snap.dominant });
    this.trackedSince = null;
    this.running = true;
    this.patch({ ui: "calibrating" });
    this.schedule(gen);
  }

  private schedule(gen: number): void {
    const video = this.video;
    if (!this.running || gen !== this.generation || !video) return;
    const next = () => void this.tick(gen);
    if ("requestVideoFrameCallback" in video) video.requestVideoFrameCallback(next);
    else requestAnimationFrame(next);
  }

  private async tick(gen: number): Promise<void> {
    if (!this.running || gen !== this.generation) return;
    const now = performance.now();
    const engine = this.engine;
    if (engine && this.video && !engine.busy && now - this.lastFrame >= FRAME_INTERVAL_MS) {
      this.lastFrame = now;
      const frame = await engine.detect(this.video, now);
      if (frame && this.running && gen === this.generation && this.recognizer) {
        const events = this.recognizer.update(frame);
        const pointer = this.adapter?.apply(events);
        const tracking = this.recognizer.tracking;
        const p: Partial<GestureSnapshot> = { tracking, phase: this.recognizer.phase };
        if (pointer !== undefined) p.pointer = pointer;
        if (this.snap.ui === "calibrating") {
          if (tracking === "tracked") {
            this.trackedSince ??= now;
            if (now - this.trackedSince >= CALIBRATION_MS) p.ui = "active";
          } else this.trackedSince = null;
        }
        this.patch(p);
      }
    }
    this.schedule(gen);
  }

  private teardown(): void {
    this.generation++;
    this.running = false;
    const events = this.recognizer?.stop() ?? [];
    this.adapter?.apply(events);
    this.controller?.dispatch({ type: "hoverEnd" });
    this.recognizer = null;
    this.engine?.dispose();
    this.engine = null;
    this.camera?.onChange(null);
    this.camera?.stop();
    this.camera = null;
    this.trackedSince = null;
  }

  private fail(failure: GestureFailure): void {
    this.teardown();
    this.patch({ ui: "failed", failure, pointer: null, tracking: "searching", phase: "idle" });
  }

  stop(reason: "user" | "hidden" = "user"): void {
    if (this.snap.ui === "off") return;
    this.teardown();
    this.patch({ ui: reason === "hidden" ? "failed" : "off", failure: reason === "hidden" ? "hidden" : null, pointer: null, tracking: "searching", phase: "idle" });
  }

  get active(): boolean {
    return this.snap.ui === "starting" || this.snap.ui === "loading" || this.snap.ui === "calibrating" || this.snap.ui === "active";
  }

}
