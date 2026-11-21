/**
 * CameraSession — camera permission and stream lifecycle, nothing else.
 *
 * Starts only on an explicit call (the UI calls it from a click), requests video only, reports the
 * real outcome (never a faked "on"), and stops every track on stop(), including when stop() races a
 * pending permission prompt. The stream is attached to a local <video> element and never leaves it.
 */

export type CameraState = "off" | "requesting" | "live" | "denied" | "unavailable" | "in_use" | "insecure" | "ended" | "error";

export interface MediaEnvironment {
  isSecureContext: boolean;
  mediaDevices?: Pick<MediaDevices, "getUserMedia">;
}

export function classifyCameraError(err: unknown): CameraState {
  const name = (err as { name?: string } | null)?.name ?? "";
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") return "denied";
  if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") return "unavailable";
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") return "in_use";
  return "error";
}

export class CameraSession {
  state: CameraState = "off";
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private generation = 0;
  private listener: ((s: CameraState) => void) | null = null;

  constructor(private readonly env: MediaEnvironment) {}

  onChange(listener: ((s: CameraState) => void) | null): void {
    this.listener = listener;
  }

  private set(s: CameraState): void {
    this.state = s;
    this.listener?.(s);
  }

  async start(video: HTMLVideoElement): Promise<CameraState> {
    if (this.state === "requesting" || this.state === "live") return this.state;
    if (!this.env.isSecureContext) {
      this.set("insecure");
      return this.state;
    }
    if (!this.env.mediaDevices?.getUserMedia) {
      this.set("unavailable");
      return this.state;
    }
    const gen = ++this.generation;
    this.set("requesting");
    let stream: MediaStream;
    try {
      stream = await this.env.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30, max: 30 } },
      });
    } catch (err) {
      if (gen === this.generation) this.set(classifyCameraError(err));
      return this.state;
    }
    if (gen !== this.generation) {
      // stop() was called while the prompt was open: release the camera immediately.
      stream.getTracks().forEach((t) => t.stop());
      return this.state;
    }
    this.stream = stream;
    this.video = video;
    for (const track of stream.getVideoTracks()) {
      // Device unplugged, permission revoked mid-session, or the OS took the camera.
      track.addEventListener("ended", () => {
        if (gen === this.generation && this.state === "live") {
          this.release();
          this.set("ended");
        }
      });
    }
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    try {
      await video.play();
    } catch {
      // Autoplay of a muted inline stream is allowed after a user gesture; if not, frames still flow.
    }
    if (gen !== this.generation) return this.state;
    this.set("live");
    return this.state;
  }

  private release(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (this.video) {
      this.video.pause();
      this.video.srcObject = null;
    }
    this.video = null;
  }

  /** Stop the camera and invalidate any pending start. Idempotent. */
  stop(): void {
    this.generation++;
    this.release();
    if (this.state !== "off") this.set("off");
  }

  /** Tracks still live (tests and diagnostics). */
  liveTracks(): number {
    return this.stream?.getTracks().filter((t) => t.readyState === "live").length ?? 0;
  }
}
