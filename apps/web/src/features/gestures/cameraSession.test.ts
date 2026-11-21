import { describe, expect, it } from "vitest";
import { CameraSession, classifyCameraError } from "./cameraSession";

class FakeTrack extends EventTarget {
  readyState: "live" | "ended" = "live";
  stop() {
    this.readyState = "ended";
  }
  unplug() {
    this.readyState = "ended";
    this.dispatchEvent(new Event("ended"));
  }
}
function fakeStream() {
  const track = new FakeTrack();
  return { track, stream: { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream };
}
function fakeVideo() {
  return { srcObject: null as unknown, muted: false, playsInline: false, play: async () => {}, pause: () => {} } as unknown as HTMLVideoElement;
}
const err = (name: string) => Object.assign(new Error(name), { name });

describe("CameraSession", () => {
  it("requests video only, goes live, and stop() releases every track", async () => {
    const { stream, track } = fakeStream();
    let constraints: MediaStreamConstraints | undefined;
    const s = new CameraSession({ isSecureContext: true, mediaDevices: { getUserMedia: async (c) => ((constraints = c), stream) } });
    const video = fakeVideo();
    expect(await s.start(video)).toBe("live");
    expect(constraints?.audio).toBe(false);
    expect(video.srcObject).toBe(stream);
    expect(s.liveTracks()).toBe(1);
    s.stop();
    expect(track.readyState).toBe("ended");
    expect(video.srcObject).toBeNull();
    expect(s.state).toBe("off");
  });

  it.each([
    ["NotAllowedError", "denied"],
    ["SecurityError", "denied"],
    ["NotFoundError", "unavailable"],
    ["OverconstrainedError", "unavailable"],
    ["NotReadableError", "in_use"],
    ["TypeError", "error"],
  ])("maps %s to %s and never claims to be live", async (name, state) => {
    const s = new CameraSession({ isSecureContext: true, mediaDevices: { getUserMedia: async () => Promise.reject(err(name)) } });
    expect(await s.start(fakeVideo())).toBe(state);
    expect(s.liveTracks()).toBe(0);
    expect(classifyCameraError(err(name))).toBe(state);
  });

  it("refuses outside a secure context and without mediaDevices", async () => {
    expect(await new CameraSession({ isSecureContext: false, mediaDevices: { getUserMedia: async () => fakeStream().stream } }).start(fakeVideo())).toBe("insecure");
    expect(await new CameraSession({ isSecureContext: true }).start(fakeVideo())).toBe("unavailable");
  });

  it("stop() during a pending permission prompt releases the camera when it arrives", async () => {
    const { stream, track } = fakeStream();
    let grant!: (s: MediaStream) => void;
    const s = new CameraSession({ isSecureContext: true, mediaDevices: { getUserMedia: () => new Promise((r) => (grant = r)) } });
    const video = fakeVideo();
    const pending = s.start(video);
    expect(s.state).toBe("requesting");
    s.stop(); // e.g. the analyst left the page while the browser prompt was open
    grant(stream);
    expect(await pending).toBe("off");
    expect(track.readyState).toBe("ended");
    expect(video.srcObject).toBeNull();
  });

  it("a device unplugged or permission revoked mid-session ends the session", async () => {
    const { stream, track } = fakeStream();
    const states: string[] = [];
    const s = new CameraSession({ isSecureContext: true, mediaDevices: { getUserMedia: async () => stream } });
    s.onChange((st) => states.push(st));
    await s.start(fakeVideo());
    track.unplug();
    expect(s.state).toBe("ended");
    expect(states).toEqual(["requesting", "live", "ended"]);
    expect(s.liveTracks()).toBe(0);
  });
});
