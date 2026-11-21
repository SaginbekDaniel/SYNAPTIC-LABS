/**
 * Hand-landmark types and pose features. Pure functions over the 21-point MediaPipe hand model
 * (https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker — index layout below).
 * Coordinates are normalised to the camera frame: x, y ∈ [0, 1], origin top-left, *not* mirrored.
 */

export interface Landmark {
  x: number;
  y: number;
  z: number;
}

export interface Hand {
  handedness: "Left" | "Right";
  /** Handedness confidence reported by the model, 0–1. */
  score: number;
  landmarks: Landmark[];
}

export interface LandmarkFrame {
  /** Monotonic capture time, ms. */
  t: number;
  hands: Hand[];
}

export const LM = {
  WRIST: 0,
  THUMB_TIP: 4,
  INDEX_MCP: 5,
  INDEX_PIP: 6,
  INDEX_TIP: 8,
  MIDDLE_MCP: 9,
  MIDDLE_PIP: 10,
  MIDDLE_TIP: 12,
  RING_MCP: 13,
  RING_PIP: 14,
  RING_TIP: 16,
  PINKY_MCP: 17,
  PINKY_PIP: 18,
  PINKY_TIP: 20,
} as const;

export type Pose = "open" | "point" | "pinch" | "other";

export interface PoseThresholds {
  /** Pinch starts below this thumb–index distance (in hand-scale units)… */
  pinchOn: number;
  /** …and ends only above this one (hysteresis). */
  pinchOff: number;
  /** A finger is extended when its tip is this much farther from the wrist than its PIP joint. */
  extendRatio: number;
  /**
   * A pinch needs the index tip at least this far from the wrist (hand-scale units). In a fist the
   * thumb rests on the curled index finger, close to its tip; without this, a fist reads as a pinch.
   */
  pinchMinReach: number;
}

export const DEFAULT_POSE_THRESHOLDS: PoseThresholds = { pinchOn: 0.32, pinchOff: 0.5, extendRatio: 1.12, pinchMinReach: 1.15 };

const MISSING: Landmark = { x: Number.NaN, y: Number.NaN, z: Number.NaN };
/** Landmark i, or a NaN point — NaN fails every comparison, so a malformed hand never matches a pose. */
export const pt = (h: Hand, i: number): Landmark => h.landmarks[i] ?? MISSING;
const dist = (a: Landmark, b: Landmark) => Math.hypot(a.x - b.x, a.y - b.y);

export function isValidHand(h: Hand): boolean {
  return h.landmarks.length === 21 && h.landmarks.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)) && handScale(h) > 1e-4;
}

/** Wrist → middle-finger MCP: a size reference that does not change when fingers bend. */
export function handScale(h: Hand): number {
  return dist(pt(h, LM.WRIST), pt(h, LM.MIDDLE_MCP));
}

export function pinchDistance(h: Hand): number {
  return dist(pt(h, LM.THUMB_TIP), pt(h, LM.INDEX_TIP)) / handScale(h);
}

function extended(h: Hand, tip: number, pip: number, ratio: number): boolean {
  const w = pt(h, LM.WRIST);
  return dist(pt(h, tip), w) > dist(pt(h, pip), w) * ratio;
}

/**
 * Classify one hand. `wasPinching` applies the release threshold instead of the activation
 * threshold, so a pinch hovering near the boundary does not flicker.
 */
export function classifyPose(h: Hand, wasPinching: boolean, th: PoseThresholds = DEFAULT_POSE_THRESHOLDS): Pose {
  const pinch = pinchDistance(h);
  const reach = dist(pt(h, LM.INDEX_TIP), pt(h, LM.WRIST)) / handScale(h);
  if (pinch < (wasPinching ? th.pinchOff : th.pinchOn) && reach >= th.pinchMinReach) return "pinch";
  const index = extended(h, LM.INDEX_TIP, LM.INDEX_PIP, th.extendRatio);
  const middle = extended(h, LM.MIDDLE_TIP, LM.MIDDLE_PIP, th.extendRatio);
  const ring = extended(h, LM.RING_TIP, LM.RING_PIP, th.extendRatio);
  const pinky = extended(h, LM.PINKY_TIP, LM.PINKY_PIP, th.extendRatio);
  if (index && middle && ring && pinky && pinch > th.pinchOff) return "open";
  if (index && !middle && !ring && !pinky) return "point";
  return "other";
}

/** Where the pointer is for a pose: index tip when pointing, pinch midpoint when pinching, palm otherwise. */
export function anchor(h: Hand, pose: Pose): { x: number; y: number } {
  const thumb = pt(h, LM.THUMB_TIP);
  const index = pt(h, LM.INDEX_TIP);
  if (pose === "pinch") return { x: (thumb.x + index.x) / 2, y: (thumb.y + index.y) / 2 };
  if (pose === "point") return { x: index.x, y: index.y };
  const palm = [LM.WRIST, LM.INDEX_MCP, LM.MIDDLE_MCP, LM.RING_MCP, LM.PINKY_MCP].map((i) => pt(h, i));
  return { x: palm.reduce((s, p) => s + p.x, 0) / palm.length, y: palm.reduce((s, p) => s + p.y, 0) / palm.length };
}
