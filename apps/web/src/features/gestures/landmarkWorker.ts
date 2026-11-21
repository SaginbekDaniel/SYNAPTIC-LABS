/// <reference lib="webworker" />
/**
 * Hand-landmark worker. Runs MediaPipe Hand Landmarker off the main thread on frames the page
 * transfers in, and returns 21 landmarks per hand. Frames and landmarks exist only in memory here:
 * nothing is stored, logged or sent. The same-origin guard is installed before MediaPipe is loaded,
 * so the library's built-in usage-metrics upload cannot leave the browser.
 */
import type { HandLandmarker } from "@mediapipe/tasks-vision";
import type { Hand } from "./landmarks";
import { installSameOriginGuard } from "./sameOriginGuard";

declare const self: DedicatedWorkerGlobalScope;
installSameOriginGuard(self as unknown as Parameters<typeof installSameOriginGuard>[0]);

export type WorkerRequest = { type: "init"; wasmBase: string; model: string } | { type: "frame"; bitmap: ImageBitmap; t: number } | { type: "close" };
export type WorkerResponse = { type: "ready" } | { type: "result"; t: number; hands: Hand[] } | { type: "error"; code: "init_failed" | "inference_failed" };

let landmarker: HandLandmarker | null = null;
const post = (m: WorkerResponse) => self.postMessage(m);

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const msg = event.data;
  if (msg.type === "init") {
    try {
      const { FilesetResolver, HandLandmarker } = await import("@mediapipe/tasks-vision");
      // `true`: the ES-module loader, which works inside a module worker.
      const fileset = await FilesetResolver.forVisionTasks(msg.wasmBase, true);
      landmarker = await HandLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: msg.model, delegate: "CPU" },
        runningMode: "VIDEO",
        numHands: 2,
        minHandDetectionConfidence: 0.6,
        minHandPresenceConfidence: 0.6,
        minTrackingConfidence: 0.5,
      });
      post({ type: "ready" });
    } catch {
      post({ type: "error", code: "init_failed" });
    }
    return;
  }
  if (msg.type === "frame") {
    try {
      if (!landmarker) return;
      const r = landmarker.detectForVideo(msg.bitmap, msg.t);
      const hands: Hand[] = r.landmarks.map((points, i) => {
        const h = r.handedness[i]?.[0];
        return {
          handedness: h?.categoryName === "Left" ? "Left" : "Right",
          score: h?.score ?? 0,
          landmarks: points.map((p) => ({ x: p.x, y: p.y, z: p.z })),
        };
      });
      post({ type: "result", t: msg.t, hands });
    } catch {
      post({ type: "error", code: "inference_failed" });
    } finally {
      msg.bitmap.close();
    }
    return;
  }
  if (msg.type === "close") {
    try {
      landmarker?.close();
    } finally {
      landmarker = null;
      self.close();
    }
  }
};
