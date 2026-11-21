/**
 * GestureRecognizer — a pure, deterministic state machine from landmark frames to gesture events.
 *
 * It owns no timers and touches no DOM: time comes from the frames, so every behaviour is
 * reproducible in tests with synthetic landmarks. Safety contract:
 *  - a pose activates only after it has been stable for `holdMs`; a pinch ends only after it has been
 *    released for `releaseMs` (and its distance threshold has hysteresis);
 *  - losing the hand for `lostMs`, an ambiguous second hand, or `stop()` cancels whatever was active
 *    and emits `cancel` — never `dragEnd` or `tap`, so nothing is committed on uncertain input;
 *  - after a gesture ends, new activations wait `cooldownMs`;
 *  - duplicate and out-of-order frames are ignored.
 * Events only describe pointer movement; mapping them to (non-destructive) graph commands is the
 * adapter's job.
 */
import { anchor, classifyPose, DEFAULT_POSE_THRESHOLDS, isValidHand, type Hand, type LandmarkFrame, type Pose, type PoseThresholds } from "./landmarks";
import { PointFilter } from "./oneEuro";

export type Phase = "idle" | "hover" | "panning" | "pinching" | "dragging" | "zooming";
export type Tracking = "searching" | "tracked" | "lost";

/** Viewport-normalised coordinates: (0,0) top-left of the graph stage, (1,1) bottom-right. */
export type GestureEvent =
  | { type: "pointer"; x: number; y: number; pose: Pose }
  | { type: "pointerLost" }
  | { type: "pan"; dx: number; dy: number }
  | { type: "tap"; x: number; y: number }
  | { type: "dragStart"; x: number; y: number }
  | { type: "dragMove"; x: number; y: number }
  | { type: "dragEnd" }
  | { type: "zoom"; factor: number; x: number; y: number }
  | { type: "cancel"; reason: "lost" | "ambiguous" | "stopped" };

export const GESTURE_EVENT_TYPES: readonly GestureEvent["type"][] = ["pointer", "pointerLost", "pan", "tap", "dragStart", "dragMove", "dragEnd", "zoom", "cancel"];

export interface RecognizerOptions {
  holdMs: number;
  releaseMs: number;
  lostMs: number;
  cooldownMs: number;
  /** Pinch movement (normalised) that turns a pinch into a drag instead of a tap. */
  dragThreshold: number;
  /** Ignore palm movement below this (normalised) per frame while panning. */
  panDeadzone: number;
  /** Minimum handedness score for a hand to count. */
  minScore: number;
  dominant: "Left" | "Right";
  /** Selfie view: the camera image is mirrored so moving right moves the pointer right. */
  mirror: boolean;
  /** Fraction of the camera frame ignored at each edge; the inner region maps to the whole stage. */
  margin: number;
  thresholds: PoseThresholds;
}

export const DEFAULT_RECOGNIZER_OPTIONS: RecognizerOptions = {
  holdMs: 180,
  releaseMs: 90,
  lostMs: 300,
  cooldownMs: 250,
  dragThreshold: 0.025,
  panDeadzone: 0.0015,
  minScore: 0.6,
  dominant: "Right",
  mirror: true,
  margin: 0.12,
  thresholds: DEFAULT_POSE_THRESHOLDS,
};

type Point = { x: number; y: number };
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);

export class GestureRecognizer {
  phase: Phase = "idle";
  tracking: Tracking = "searching";
  private readonly o: RecognizerOptions;
  private lastT = Number.NEGATIVE_INFINITY;
  private lastSeen = Number.NEGATIVE_INFINITY;
  private candidate: { pose: Pose; since: number } | null = null;
  private releaseSince: number | null = null;
  private pinchOrigin: Point | null = null;
  private lastPan: Point | null = null;
  private lastZoomDistance: number | null = null;
  private zoomSince: number | null = null;
  private cooldownUntil = Number.NEGATIVE_INFINITY;
  private readonly filter = new PointFilter();

  constructor(options: Partial<RecognizerOptions> = {}) {
    this.o = { ...DEFAULT_RECOGNIZER_OPTIONS, ...options, thresholds: { ...DEFAULT_RECOGNIZER_OPTIONS.thresholds, ...options.thresholds } };
  }

  setDominant(hand: "Left" | "Right"): void {
    this.o.dominant = hand;
  }

  /** Map a camera-frame point into the stage, mirrored and with the edge margin removed. */
  private toStage(p: Point): Point {
    const x = this.o.mirror ? 1 - p.x : p.x;
    const span = 1 - 2 * this.o.margin;
    return { x: clamp01((x - this.o.margin) / span), y: clamp01((p.y - this.o.margin) / span) };
  }

  private get pinchActive(): boolean {
    return this.phase === "pinching" || this.phase === "dragging";
  }

  /** Cancel anything in progress. Emits `cancel` only if a gesture was actually active. */
  private abort(reason: "lost" | "ambiguous" | "stopped"): GestureEvent[] {
    const active = this.phase === "panning" || this.phase === "pinching" || this.phase === "dragging" || this.phase === "zooming";
    this.phase = "idle";
    this.candidate = null;
    this.releaseSince = null;
    this.pinchOrigin = null;
    this.lastPan = null;
    this.lastZoomDistance = null;
    this.zoomSince = null;
    this.filter.reset();
    return active ? [{ type: "cancel", reason }] : [];
  }

  /** Explicit stop (camera off, tab hidden, route change). */
  stop(): GestureEvent[] {
    const events = this.abort("stopped");
    this.tracking = "searching";
    this.lastSeen = Number.NEGATIVE_INFINITY;
    return events;
  }

  update(frame: LandmarkFrame): GestureEvent[] {
    const t = frame.t;
    if (!Number.isFinite(t) || t <= this.lastT) return [];
    this.lastT = t;
    const hands = frame.hands.filter((h) => h.score >= this.o.minScore && isValidHand(h));

    if (hands.length === 0) {
      if (this.tracking === "tracked" && t - this.lastSeen >= this.o.lostMs) {
        const events = this.abort("lost");
        this.tracking = "lost";
        return [...events, { type: "pointerLost" }];
      }
      return [];
    }
    this.lastSeen = t;
    this.tracking = "tracked";

    if (hands.length >= 2) {
      const zoom = this.twoHands(hands, t);
      if (zoom) return zoom;
    } else if (this.phase === "zooming") {
      // One hand left the zoom: end it quietly and wait for a fresh, stable pose.
      this.phase = "idle";
      this.lastZoomDistance = null;
      this.zoomSince = null;
      this.candidate = null;
      this.cooldownUntil = t + this.o.cooldownMs;
    }
    return this.oneHand(this.primary(hands as [Hand, ...Hand[]]), t);
  }

  /** Caller guarantees at least one hand. */
  private primary(hands: [Hand, ...Hand[]]): Hand {
    return hands.find((h) => h.handedness === this.o.dominant) ?? [...hands].sort((a, b) => b.score - a.score)[0] ?? hands[0];
  }

  /** Two pinching hands = zoom. Returns null when the frame is not a zoom frame. */
  private twoHands(hands: Hand[], t: number): GestureEvent[] | null {
    const [a, b] = [...hands].sort((x, y) => y.score - x.score || (x.handedness < y.handedness ? -1 : 1));
    if (!a || !b) return null;
    const pa = classifyPose(a, this.phase === "zooming", this.o.thresholds);
    const pb = classifyPose(b, this.phase === "zooming", this.o.thresholds);
    if (pa !== "pinch" || pb !== "pinch") {
      if (this.phase === "zooming") {
        this.phase = "idle";
        this.lastZoomDistance = null;
        this.zoomSince = null;
        this.cooldownUntil = t + this.o.cooldownMs;
      }
      return null;
    }
    // A second hand appearing mid-drag/pan is ambiguous: cancel rather than guess.
    const events: GestureEvent[] = this.pinchActive || this.phase === "panning" ? this.abort("ambiguous") : [];
    const ma = this.toStage(anchor(a, "pinch"));
    const mb = this.toStage(anchor(b, "pinch"));
    const d = distance(ma, mb);
    const mid = { x: (ma.x + mb.x) / 2, y: (ma.y + mb.y) / 2 };
    if (this.phase !== "zooming") {
      if (t < this.cooldownUntil) return events;
      this.zoomSince ??= t;
      if (t - this.zoomSince < this.o.holdMs) return events;
      this.phase = "zooming";
      this.lastZoomDistance = d;
      return events;
    }
    const prev = this.lastZoomDistance ?? d;
    this.lastZoomDistance = d;
    if (prev > 1e-3 && d > 1e-3 && Math.abs(d - prev) > 1e-3) events.push({ type: "zoom", factor: d / prev, x: mid.x, y: mid.y });
    return events;
  }

  private oneHand(h: Hand, t: number): GestureEvent[] {
    this.zoomSince = null;
    const pose = classifyPose(h, this.pinchActive || this.candidate?.pose === "pinch", this.o.thresholds);
    const p = this.filter.filter(this.toStage(anchor(h, pose)), t);
    const events: GestureEvent[] = [{ type: "pointer", x: p.x, y: p.y, pose }];
    if (!this.candidate || this.candidate.pose !== pose) this.candidate = { pose, since: t };
    const stable = t - this.candidate.since >= this.o.holdMs;

    if (this.pinchActive) {
      if (pose === "pinch") {
        this.releaseSince = null;
        const origin = this.pinchOrigin!;
        if (this.phase === "pinching" && distance(origin, p) > this.o.dragThreshold) {
          this.phase = "dragging";
          events.push({ type: "dragStart", x: origin.x, y: origin.y });
        }
        if (this.phase === "dragging") events.push({ type: "dragMove", x: p.x, y: p.y });
        return events;
      }
      this.releaseSince ??= t;
      if (t - this.releaseSince < this.o.releaseMs) return events;
      events.push(this.phase === "dragging" ? { type: "dragEnd" } : { type: "tap", x: this.pinchOrigin!.x, y: this.pinchOrigin!.y });
      this.phase = "idle";
      this.pinchOrigin = null;
      this.releaseSince = null;
      this.cooldownUntil = t + this.o.cooldownMs;
      return events;
    }

    if (this.phase === "panning") {
      if (pose === "open") {
        this.releaseSince = null;
        const last = this.lastPan ?? p;
        const dx = p.x - last.x;
        const dy = p.y - last.y;
        if (Math.hypot(dx, dy) > this.o.panDeadzone) {
          events.push({ type: "pan", dx, dy });
          this.lastPan = p;
        }
        return events;
      }
      this.releaseSince ??= t;
      if (t - this.releaseSince < this.o.releaseMs) return events;
      this.phase = "idle";
      this.lastPan = null;
      this.releaseSince = null;
      this.cooldownUntil = t + this.o.cooldownMs;
    }

    if (t < this.cooldownUntil || !stable) {
      this.phase = pose === "point" ? "hover" : "idle";
      return events;
    }
    if (pose === "pinch") {
      this.phase = "pinching";
      this.pinchOrigin = p;
    } else if (pose === "open") {
      this.phase = "panning";
      this.lastPan = p;
    } else {
      this.phase = pose === "point" ? "hover" : "idle";
    }
    return events;
  }
}
