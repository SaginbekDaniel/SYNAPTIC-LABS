/**
 * Synthetic 21-point hands for deterministic tests and the mocked-landmark E2E source.
 * Geometry is a simplified upright hand: wrist below the palm, fingers pointing up (−y).
 */
import type { Hand, Landmark } from "./landmarks";

export type SyntheticPose = "open" | "point" | "pinch" | "fist";

export interface SyntheticHandOptions {
  /** Palm centre (middle-finger MCP), camera-normalised. */
  x: number;
  y: number;
  /** Wrist → middle MCP distance (hand scale). */
  scale?: number;
  handedness?: "Left" | "Right";
  score?: number;
  /** For pinch: thumb–index gap in hand-scale units (default 0.05 = closed). */
  pinchGap?: number;
}

export function syntheticHand(pose: SyntheticPose, o: SyntheticHandOptions): Hand {
  const s = o.scale ?? 0.15;
  const at = (dx: number, dy: number): Landmark => ({ x: o.x + dx * s, y: o.y + dy * s, z: 0 });
  const mcp = { index: [-0.25, 0.05], middle: [0, 0], ring: [0.25, 0.05], pinky: [0.45, 0.15] } as const;
  const finger = (base: readonly [number, number], up: boolean): Landmark[] => {
    const [bx, by] = base;
    // pip, dip, tip — extended fingers point away from the wrist; curled tips fold back toward it.
    return up ? [at(bx, by - 0.35), at(bx, by - 0.6), at(bx, by - 0.8)] : [at(bx, by - 0.3), at(bx, by - 0.15), at(bx, by + 0.05)];
  };
  const up = { index: pose === "open" || pose === "point", middle: pose === "open", ring: pose === "open", pinky: pose === "open" };
  const index = finger(mcp.index, up.index);
  let thumbTip: Landmark;
  if (pose === "pinch") {
    // Index bends toward the thumb; the two tips meet at a gap measured in hand-scale units.
    index[2] = at(-0.45, -0.45);
    thumbTip = at(-0.45 + (o.pinchGap ?? 0.05), -0.45);
  } else if (pose === "open") {
    thumbTip = at(-0.75, 0.2);
  } else {
    thumbTip = at(-0.15, 0.35);
  }
  const lm: Landmark[] = [
    at(0, 1), // 0 wrist
    at(-0.35, 0.75), // 1 thumb cmc
    at(-0.5, 0.5), // 2 thumb mcp
    at(-0.55, 0.3), // 3 thumb ip
    thumbTip, // 4 thumb tip
    at(...mcp.index), // 5
    ...index, // 6-8
    at(...mcp.middle), // 9
    ...finger(mcp.middle, up.middle), // 10-12
    at(...mcp.ring), // 13
    ...finger(mcp.ring, up.ring), // 14-16
    at(...mcp.pinky), // 17
    ...finger(mcp.pinky, up.pinky), // 18-20
  ];
  return { handedness: o.handedness ?? "Right", score: o.score ?? 0.95, landmarks: lm };
}
