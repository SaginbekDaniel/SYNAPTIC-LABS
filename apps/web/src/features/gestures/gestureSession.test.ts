import { describe, expect, it } from "vitest";
import type { GraphController } from "../../components/graph/controller";
import type { CameraState } from "./cameraSession";
import { GestureSession, type CameraPort, type EnginePort, type GestureUi } from "./gestureSession";

/** A promise the test resolves or rejects by hand. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
  return { promise, resolve, reject };
}

function harness(opts: { controller?: boolean } = {}) {
  const log: string[] = [];
  const engineReady = deferred<void>();
  const cameraResult = deferred<CameraState>();
  let engineError: (() => void) | null = null;
  let cameraListener: ((s: CameraState) => void) | null = null;
  const engine: EnginePort = {
    busy: false,
    start: async (onError) => {
      log.push("engine.start");
      engineError = () => onError(Object.assign(new Error("inference_failed"), { code: "inference_failed" }) as never);
      await engineReady.promise;
      log.push("engine.ready");
    },
    detect: async () => null,
    dispose: () => void log.push("engine.dispose"),
  };
  const camera: CameraPort = {
    start: async () => {
      log.push("camera.start");
      return cameraResult.promise;
    },
    stop: () => void log.push("camera.stop"),
    onChange: (l) => void (cameraListener = l),
  };
  const session = new GestureSession({
    createCamera: () => (log.push("camera.create"), camera),
    createEngine: () => (log.push("engine.create"), engine),
  });
  const uis: GestureUi[] = [];
  session.subscribe(() => {
    const ui = session.getSnapshot().ui;
    if (uis[uis.length - 1] !== ui) uis.push(ui);
  });
  // The session only needs a video element to hand to the camera and a controller to drive.
  session.attachVideo({ requestVideoFrameCallback: () => 0 } as unknown as HTMLVideoElement);
  const controller = { dispatch: () => true, stageSize: () => ({ width: 800, height: 600 }) } as unknown as GraphController;
  if (opts.controller !== false) session.setController(controller);
  session.requestConsent();
  const flush = () => new Promise((r) => setTimeout(r, 0));
  return { session, controller, log, uis, engineReady, cameraResult, flush, fireEngineError: () => engineError?.(), endCamera: () => cameraListener?.("ended") };
}

describe("GestureSession start order (model before camera, H-05)", () => {
  it("loads the model, then requests the camera, then calibrates", async () => {
    const h = harness();
    const started = h.session.start();
    await h.flush();
    expect(h.session.getSnapshot().ui).toBe("loading");
    expect(h.log).toEqual(["engine.create", "engine.start"]); // no camera object, no camera request yet

    h.engineReady.resolve();
    await h.flush();
    expect(h.session.getSnapshot().ui).toBe("starting");
    expect(h.log).toEqual(["engine.create", "engine.start", "engine.ready", "camera.create", "camera.start"]);

    h.cameraResult.resolve("live");
    await started;
    expect(h.uis).toEqual(["consent", "loading", "starting", "calibrating"]);
  });

  it("stopping while the model loads never touches the camera and disposes the engine", async () => {
    const h = harness();
    const started = h.session.start();
    await h.flush();
    h.session.stop();
    h.engineReady.resolve();
    await started;
    expect(h.log.filter((e) => e.startsWith("camera"))).toEqual([]);
    expect(h.log).toContain("engine.dispose");
    expect(h.session.getSnapshot().ui).toBe("off");
  });

  it("a hidden tab while the model loads fails safe without a camera request", async () => {
    const h = harness();
    const started = h.session.start();
    await h.flush();
    h.session.stop("hidden");
    h.engineReady.resolve();
    await started;
    expect(h.log.filter((e) => e.startsWith("camera"))).toEqual([]);
    expect(h.session.getSnapshot()).toMatchObject({ ui: "failed", failure: "hidden" });
  });

  it("a model that fails to load never asks for the camera", async () => {
    const h = harness();
    const started = h.session.start();
    await h.flush();
    h.engineReady.reject(new Error("timeout"));
    await started;
    expect(h.log.filter((e) => e.startsWith("camera"))).toEqual([]);
    expect(h.session.getSnapshot()).toMatchObject({ ui: "failed", failure: "engine" });
  });

  it("stopping during the camera prompt stops the camera and disposes the engine", async () => {
    const h = harness();
    const started = h.session.start();
    h.engineReady.resolve();
    await h.flush();
    expect(h.session.getSnapshot().ui).toBe("starting");
    h.session.stop();
    h.cameraResult.resolve("live"); // the prompt was answered after the user had already stopped
    await started;
    expect(h.log).toEqual(expect.arrayContaining(["camera.stop", "engine.dispose"]));
    expect(h.session.getSnapshot().ui).toBe("off");
  });

  it("a denied camera releases the loaded engine and reports the denial", async () => {
    const h = harness();
    const started = h.session.start();
    h.engineReady.resolve();
    await h.flush();
    h.cameraResult.resolve("denied");
    await started;
    expect(h.log).toEqual(expect.arrayContaining(["engine.dispose", "camera.stop"]));
    expect(h.session.getSnapshot()).toMatchObject({ ui: "failed", failure: "denied" });
  });

  it("an engine failure while the camera prompt is open stops the camera", async () => {
    const h = harness();
    const started = h.session.start();
    h.engineReady.resolve();
    await h.flush();
    h.fireEngineError();
    expect(h.session.getSnapshot()).toMatchObject({ ui: "failed", failure: "engine" });
    expect(h.log).toEqual(expect.arrayContaining(["camera.stop", "engine.dispose"]));
    h.cameraResult.resolve("live");
    await started;
    expect(h.session.getSnapshot().ui).toBe("failed"); // the late grant does not revive the session
  });

  it("a camera that ends mid-session fails the session and releases everything", async () => {
    const h = harness();
    const started = h.session.start();
    h.engineReady.resolve();
    await h.flush();
    h.cameraResult.resolve("live");
    await started;
    h.endCamera();
    expect(h.session.getSnapshot()).toMatchObject({ ui: "failed", failure: "ended" });
    expect(h.log).toEqual(expect.arrayContaining(["camera.stop", "engine.dispose"]));
  });

  it("a start clicked while the graph is still being laid out runs once the graph can be driven", async () => {
    const h = harness({ controller: false });
    await h.session.start();
    expect(h.log).toEqual([]); // nothing yet: no controller
    expect(h.session.getSnapshot().ui).toBe("consent");
    h.session.setController(h.controller);
    await h.flush();
    expect(h.session.getSnapshot().ui).toBe("loading");
    expect(h.log).toEqual(["engine.create", "engine.start"]);
  });

  it("a remembered start is dropped when the consent is dismissed first", async () => {
    const h = harness({ controller: false });
    await h.session.start();
    h.session.dismissConsent();
    h.session.setController(h.controller);
    await h.flush();
    expect(h.log).toEqual([]);
    expect(h.session.getSnapshot().ui).toBe("off");
  });
});
