import { describe, expect, it } from "vitest";
import { classifyPose, pinchDistance } from "./landmarks";
import { GESTURE_EVENT_TYPES, GestureRecognizer, type GestureEvent } from "./recognizer";
import { syntheticHand, type SyntheticHandOptions, type SyntheticPose } from "./syntheticHands";

const FRAME = 33; // ~30 FPS

/** Feed a sequence of (pose, position) frames; returns every event with its frame time. */
function run(r: GestureRecognizer, steps: { pose: SyntheticPose | null; at?: SyntheticHandOptions; ms?: number }[], t0 = 1000) {
  const out: (GestureEvent & { t: number })[] = [];
  let t = t0;
  for (const step of steps) {
    const frames = Math.max(1, Math.round((step.ms ?? FRAME) / FRAME));
    for (let i = 0; i < frames; i++) {
      t += FRAME;
      const hands = step.pose ? [syntheticHand(step.pose, step.at ?? { x: 0.5, y: 0.5 })] : [];
      for (const e of r.update({ t, hands })) out.push({ ...e, t });
    }
  }
  return out;
}
const kinds = (events: GestureEvent[]) => events.filter((e) => e.type !== "pointer").map((e) => e.type);

describe("synthetic hands are classified as intended", () => {
  it.each(["open", "point", "pinch"] as const)("%s", (pose) => {
    expect(classifyPose(syntheticHand(pose, { x: 0.5, y: 0.5 }), false)).toBe(pose);
  });
  it("fist is neither open, point nor pinch — even with the thumb resting on the curled index tip", () => {
    const fist = syntheticHand("fist", { x: 0.5, y: 0.5 });
    expect(classifyPose(fist, false)).toBe("other");
    const indexTip = fist.landmarks[8]!;
    const thumbOnIndex = { ...fist, landmarks: fist.landmarks.map((p, i) => (i === 4 ? { ...indexTip, x: indexTip.x + 0.003 } : p)) };
    expect(pinchDistance(thumbOnIndex)).toBeLessThan(0.1);
    expect(classifyPose(thumbOnIndex, false)).toBe("other");
    expect(classifyPose(thumbOnIndex, true)).toBe("other");
  });
});

describe("GestureRecognizer", () => {
  it("emits only pointer-level events", () => {
    expect([...GESTURE_EVENT_TYPES].sort()).toEqual(["cancel", "dragEnd", "dragMove", "dragStart", "pan", "pointer", "pointerLost", "tap", "zoom"].sort());
  });

  it("an open palm pans only after it has been held, and the pan follows the mirrored hand", () => {
    const r = new GestureRecognizer();
    const brief = run(r, [{ pose: "open", ms: 100 }, { pose: null, ms: 400 }]);
    expect(kinds(brief)).not.toContain("pan");

    const r2 = new GestureRecognizer();
    const moves = Array.from({ length: 12 }, (_, i) => ({ pose: "open" as const, at: { x: 0.5 + i * 0.01, y: 0.5 } }));
    const events = run(r2, [{ pose: "open", ms: 250 }, ...moves]);
    const pans = events.filter((e): e is Extract<GestureEvent, { type: "pan" }> & { t: number } => e.type === "pan");
    expect(pans.length).toBeGreaterThan(3);
    // Hand moves right in the camera image → selfie view → content moves left on screen.
    expect(pans.reduce((s, e) => s + e.dx, 0)).toBeLessThan(0);
    expect(r2.phase).toBe("panning");
  });

  it("filters jitter: a still palm with sensor noise produces (almost) no pan", () => {
    const r = new GestureRecognizer();
    let seed = 7;
    const noise = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 0.006;
    const still = Array.from({ length: 60 }, () => ({ pose: "open" as const, at: { x: 0.5 + noise(), y: 0.5 + noise() } }));
    const events = run(r, [{ pose: "open", ms: 250 }, ...still]);
    const drift = events.filter((e) => e.type === "pan").reduce((s, e) => s + Math.hypot((e as { dx: number }).dx, (e as { dy: number }).dy), 0);
    expect(drift).toBeLessThan(0.02);
  });

  it("a short pinch without movement is a tap at the pinch point — no drag", () => {
    const r = new GestureRecognizer();
    const events = run(r, [{ pose: "point", ms: 300 }, { pose: "pinch", ms: 300 }, { pose: "point", ms: 200 }]);
    expect(kinds(events)).toEqual(["tap"]);
    expect(r.phase).toBe("hover");
  });

  it("pinch + movement is a drag that starts at the pinch origin and ends on release", () => {
    const r = new GestureRecognizer();
    const path = Array.from({ length: 10 }, (_, i) => ({ pose: "pinch" as const, at: { x: 0.5 - i * 0.012, y: 0.5 } }));
    const events = run(r, [{ pose: "pinch", ms: 250 }, ...path, { pose: "point", ms: 200 }]);
    const k = kinds(events);
    expect(k[0]).toBe("dragStart");
    expect(k.at(-1)).toBe("dragEnd");
    expect(k).not.toContain("tap");
    const start = events.find((e) => e.type === "dragStart") as { x: number };
    const lastMove = events.filter((e) => e.type === "dragMove").at(-1) as { x: number };
    expect(lastMove.x).toBeGreaterThan(start.x); // mirrored: hand moved left in camera → right on stage
  });

  it("pinch hysteresis: a gap between the on and off thresholds keeps the pinch held", () => {
    const wobble = syntheticHand("pinch", { x: 0.5, y: 0.5, pinchGap: 0.42 });
    expect(pinchDistance(wobble)).toBeGreaterThan(0.32);
    expect(pinchDistance(wobble)).toBeLessThan(0.5);
    const r = new GestureRecognizer();
    run(r, [{ pose: "pinch", ms: 250 }]);
    expect(r.phase).toBe("pinching");
    let t = 5000;
    const events: GestureEvent[] = [];
    for (let i = 0; i < 20; i++) events.push(...r.update({ t: (t += FRAME), hands: [i % 2 ? wobble : syntheticHand("pinch", { x: 0.5, y: 0.5 })] }));
    expect(kinds(events)).toEqual([]);
    expect(r.phase).toBe("pinching");
  });

  it("losing the hand mid-drag cancels — never commits a dragEnd or a tap", () => {
    const r = new GestureRecognizer();
    const path = Array.from({ length: 6 }, (_, i) => ({ pose: "pinch" as const, at: { x: 0.5 + i * 0.015, y: 0.5 } }));
    const events = run(r, [{ pose: "pinch", ms: 250 }, ...path, { pose: null, ms: 500 }]);
    const k = kinds(events);
    expect(k).toContain("dragStart");
    expect(k.slice(-2)).toEqual(["cancel", "pointerLost"]);
    expect(k).not.toContain("dragEnd");
    expect(k).not.toContain("tap");
    expect((events.find((e) => e.type === "cancel") as { reason: string }).reason).toBe("lost");
    expect(r.phase).toBe("idle");
    expect(r.tracking).toBe("lost");
  });

  it("a dropout shorter than lostMs does not cancel the drag", () => {
    const r = new GestureRecognizer();
    const path = Array.from({ length: 4 }, (_, i) => ({ pose: "pinch" as const, at: { x: 0.5 + i * 0.015, y: 0.5 } }));
    const events = run(r, [{ pose: "pinch", ms: 250 }, ...path, { pose: null, ms: 130 }, { pose: "pinch", at: { x: 0.56, y: 0.5 }, ms: 100 }]);
    expect(kinds(events)).not.toContain("cancel");
    expect(r.phase).toBe("dragging");
  });

  it("ignores duplicate and out-of-order frames", () => {
    const r = new GestureRecognizer();
    const hand = syntheticHand("open", { x: 0.5, y: 0.5 });
    expect(r.update({ t: 100, hands: [hand] })).toHaveLength(1);
    expect(r.update({ t: 100, hands: [hand] })).toEqual([]);
    expect(r.update({ t: 50, hands: [hand] })).toEqual([]);
    expect(r.update({ t: Number.NaN, hands: [hand] })).toEqual([]);
  });

  it("cooldown: a pinch right after a tap does not activate", () => {
    const r = new GestureRecognizer({ cooldownMs: 600 });
    const events = run(r, [{ pose: "pinch", ms: 250 }, { pose: "point", ms: 120 }, { pose: "pinch", ms: 250 }, { pose: "point", ms: 120 }]);
    expect(kinds(events)).toEqual(["tap"]);
  });

  it("ignores low-confidence hands", () => {
    const r = new GestureRecognizer();
    const weak = syntheticHand("open", { x: 0.5, y: 0.5, score: 0.3 });
    expect(r.update({ t: 1, hands: [weak] })).toEqual([]);
    expect(r.tracking).toBe("searching");
  });

  it("two pinching hands zoom by their separation; a second hand mid-drag cancels the drag", () => {
    const r = new GestureRecognizer();
    let t = 0;
    const both = (gap: number) => [
      syntheticHand("pinch", { x: 0.5 - gap, y: 0.5, handedness: "Left" }),
      syntheticHand("pinch", { x: 0.5 + gap, y: 0.5, handedness: "Right" }),
    ];
    const events: GestureEvent[] = [];
    for (let i = 0; i < 8; i++) events.push(...r.update({ t: (t += FRAME), hands: both(0.1) }));
    for (let i = 0; i < 6; i++) events.push(...r.update({ t: (t += FRAME), hands: both(0.1 + i * 0.02) }));
    for (let i = 0; i < 6; i++) events.push(...r.update({ t: (t += FRAME), hands: both(0.2 - i * 0.02) }));
    const zooms = events.filter((e): e is Extract<GestureEvent, { type: "zoom" }> => e.type === "zoom");
    expect(zooms.some((z) => z.factor > 1)).toBe(true);
    expect(zooms.some((z) => z.factor < 1)).toBe(true);
    // Symmetric spread: the zoom anchor (midpoint of the two pinch points) does not drift.
    const spread = zooms.filter((z) => z.factor > 1);
    expect(Math.max(...spread.map((z) => z.x)) - Math.min(...spread.map((z) => z.x))).toBeLessThan(1e-9);

    const r2 = new GestureRecognizer();
    const path = Array.from({ length: 8 }, (_, i) => ({ pose: "pinch" as const, at: { x: 0.5 + i * 0.015, y: 0.5 } }));
    run(r2, [{ pose: "pinch", ms: 250 }, ...path]);
    expect(r2.phase).toBe("dragging");
    expect(r2.update({ t: 99_999, hands: both(0.1) })).toEqual([{ type: "cancel", reason: "ambiguous" }]);
  });

  it("stop() cancels an active gesture and resets tracking", () => {
    const r = new GestureRecognizer();
    run(r, [{ pose: "open", ms: 250 }]);
    expect(r.phase).toBe("panning");
    expect(r.stop()).toEqual([{ type: "cancel", reason: "stopped" }]);
    expect(r.phase).toBe("idle");
    expect(r.tracking).toBe("searching");
    expect(r.stop()).toEqual([]);
  });
});
