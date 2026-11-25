/**
 * GestureSession — orchestrates CameraSession → HandLandmarkEngine → GestureRecognizer →
 * GestureAdapter → GraphController, and owns their lifecycle.
 *
 * It is an external store (subscribe/getSnapshot) so the ~30 Hz pointer updates re-render only the
 * pointer layer, not the graph page. Every exit path — explicit stop, Escape, hidden tab, unmount,
 * camera loss, engine failure — goes through stop(), which cancels the active gesture, stops the
 * camera tracks and disposes the worker. A later start is always a new, deliberate click.
 *
 * Order on start: the recognition model is loaded first ("loading"), and only once it is ready is the
 * browser asked for the camera ("starting"). The camera is therefore never on while ~23 MB of model and
 * WASM download and initialise, i.e. never on while nothing can be recognised (H-05).
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

/** The parts of CameraSession and HandLandmarkEngine the session drives (unit tests substitute fakes). */
export type CameraPort = Pick<CameraSession, "start" | "stop" | "onChange">;
export type EnginePort = Pick<HandLandmarkEngine, "start" | "detect" | "dispose" | "busy">;
export interface GestureDeps {
  createCamera(): CameraPort;
  createEngine(): EnginePort;
}

const browserDeps: GestureDeps = {
  createCamera: () => new CameraSession({ isSecureContext: window.isSecureContext, mediaDevices: navigator.mediaDevices }),
  createEngine: () => new HandLandmarkEngine(),
};

export class GestureSession {
  private snap: GestureSnapshot = { ui: "off", failure: null, tracking: "searching", phase: "idle", pointer: null, mode: "navigate", dominant: "Right" };
  private readonly listeners = new Set<() => void>();
  private camera: CameraPort | null = null;
  private engine: EnginePort | null = null;
  private recognizer: GestureRecognizer | null = null;
  private adapter: GestureAdapter | null = null;
  private controller: GraphController | null = null;
  private video: HTMLVideoElement | null = null;
  private generation = 0;
  private running = false;
  private lastFrame = 0;
  private trackedSince: number | null = null;
  /** "Start" was clicked while the graph was still being laid out (no controller yet): start once it is. */
  private startRequested = false;

  constructor(private readonly deps: GestureDeps = browserDeps) {}

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
    if (controller && this.startRequested) void this.start();
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
    this.startRequested = false;
    if (this.snap.ui === "consent") this.patch({ ui: "off" });
  }

  /** Second, deliberate click: load the local recogniser, then start the camera. */
  async start(): Promise<void> {
    if (this.snap.ui !== "consent") {
      this.startRequested = false;
      return;
    }
    if (!this.video || !this.controller) {
      // The graph is being laid out (or rebuilt): honour the click as soon as it can be driven.
      this.startRequested = true;
      return;
    }
    this.startRequested = false;
    const gen = ++this.generation;

    // 1. The model first. No camera request has been made while this runs.
    this.patch({ ui: "loading", failure: null, tracking: "searching", phase: "idle", pointer: null });
    const engine = this.deps.createEngine();
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
      engine.dispose(); // cancelled (stop, Escape, hidden tab, unmount) while the model loaded
      return;
    }
    const video = this.video;
    if (!video) {
      this.fail("error");
      return;
    }

    // 2. Only now ask for the camera: recognition can run as soon as frames arrive.
    this.patch({ ui: "starting" });
    const camera = this.deps.createCamera();
    this.camera = camera;
    camera.onChange((state) => {
      if (gen === this.generation && state === "ended") this.fail("ended");
    });
    const state = await camera.start(video);
    if (gen !== this.generation) return; // teardown already stopped the camera and disposed the engine
    if (state !== "live") {
      this.fail(state === "off" || state === "requesting" ? "error" : state);
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
    this.startRequested = false;
    if (this.snap.ui === "off") return;
    this.teardown();
    this.patch({ ui: reason === "hidden" ? "failed" : "off", failure: reason === "hidden" ? "hidden" : null, pointer: null, tracking: "searching", phase: "idle" });
  }

  get active(): boolean {
    return this.snap.ui === "starting" || this.snap.ui === "loading" || this.snap.ui === "calibrating" || this.snap.ui === "active";
  }

}
