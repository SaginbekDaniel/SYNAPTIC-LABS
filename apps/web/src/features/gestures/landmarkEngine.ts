/**
 * HandLandmarkEngine — main-thread side of the landmark worker.
 *
 * Back-pressure by construction: one frame in flight at most; frames that arrive while the worker
 * is busy are dropped, never queued, so latency cannot build up. Assets are self-hosted under
 * /vendor/mediapipe/ (copied and hash-checked at build time by scripts/gesture-assets.mjs).
 */
import type { LandmarkFrame } from "./landmarks";
import type { WorkerRequest, WorkerResponse } from "./landmarkWorker";

export const MEDIAPIPE_BASE = `${import.meta.env.BASE_URL}vendor/mediapipe/`;
export const HAND_MODEL_PATH = `${MEDIAPIPE_BASE}hand_landmarker.task`;
const INIT_TIMEOUT_MS = 30_000;
/** Frames are downscaled before transfer: landmarks are normalised, so resolution only costs time. */
const FRAME_WIDTH = 480;

export class EngineError extends Error {
  constructor(readonly code: "init_failed" | "inference_failed" | "timeout" | "unsupported") {
    super(code);
  }
}

export class HandLandmarkEngine {
  private worker: Worker | null = null;
  private inFlight: { resolve: (f: LandmarkFrame | null) => void } | null = null;
  private onError: ((e: EngineError) => void) | null = null;

  async start(onError: (e: EngineError) => void): Promise<void> {
    if (typeof Worker === "undefined" || typeof createImageBitmap === "undefined") throw new EngineError("unsupported");
    this.onError = onError;
    const worker = new Worker(new URL("./landmarkWorker.ts", import.meta.url), { type: "module", name: "nexora-hand-landmarks" });
    this.worker = worker;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new EngineError("timeout")), INIT_TIMEOUT_MS);
      worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
        const m = e.data;
        if (m.type === "ready") {
          clearTimeout(timer);
          worker.onmessage = (ev: MessageEvent<WorkerResponse>) => this.receive(ev.data);
          resolve();
        } else if (m.type === "error") {
          clearTimeout(timer);
          reject(new EngineError(m.code));
        }
      };
      worker.onerror = () => {
        clearTimeout(timer);
        reject(new EngineError("init_failed"));
      };
      const origin = self.location.origin;
      const init: WorkerRequest = { type: "init", wasmBase: new URL(MEDIAPIPE_BASE, origin).href.replace(/\/$/, ""), model: new URL(HAND_MODEL_PATH, origin).href };
      worker.postMessage(init);
    });
  }

  private receive(m: WorkerResponse): void {
    const pending = this.inFlight;
    this.inFlight = null;
    if (m.type === "result") pending?.resolve({ t: m.t, hands: m.hands });
    else if (m.type === "error") {
      pending?.resolve(null);
      this.onError?.(new EngineError(m.code));
    }
  }

  get busy(): boolean {
    return this.inFlight !== null;
  }

  /** Detect on the current video frame, or return null at once if a frame is still in flight. */
  async detect(video: HTMLVideoElement, t: number): Promise<LandmarkFrame | null> {
    const worker = this.worker;
    if (!worker || this.inFlight || video.readyState < 2 || video.videoWidth === 0) return null;
    const scale = Math.min(1, FRAME_WIDTH / video.videoWidth);
    const bitmap = await createImageBitmap(video, { resizeWidth: Math.round(video.videoWidth * scale), resizeHeight: Math.round(video.videoHeight * scale) });
    if (this.worker !== worker || this.inFlight) {
      bitmap.close();
      return null;
    }
    return new Promise((resolve) => {
      this.inFlight = { resolve };
      const msg: WorkerRequest = { type: "frame", bitmap, t };
      worker.postMessage(msg, [bitmap]);
    });
  }

  dispose(): void {
    const worker = this.worker;
    this.worker = null;
    this.inFlight?.resolve(null);
    this.inFlight = null;
    this.onError = null;
    if (!worker) return;
    const close: WorkerRequest = { type: "close" };
    worker.postMessage(close);
    // The worker closes itself after releasing MediaPipe; terminate as a backstop.
    setTimeout(() => worker.terminate(), 2000);
  }
}
