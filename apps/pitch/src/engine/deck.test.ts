import { describe, expect, it } from "vitest";
import { STEP_COUNTS, SLIDE_COUNT, clampPos, globalIndex, next, nextSlide, parseHash, prev, prevSlide, toHash } from "./deck";

describe("deck navigation", () => {
  it("has exactly eight slides", () => expect(SLIDE_COUNT).toBe(8));

  it("walks every step forward and ends on the last state", () => {
    let p = { slide: 0, step: 0 };
    let moves = 0;
    for (;;) {
      const n = next(p);
      if (n === p) break;
      p = n;
      moves++;
    }
    expect(moves).toBe(STEP_COUNTS.reduce((a, b) => a + b, 0) - 1);
    expect(p).toEqual({ slide: SLIDE_COUNT - 1, step: STEP_COUNTS[SLIDE_COUNT - 1] - 1 });
  });

  it("going back from a slide start lands on the finished state of the previous slide", () => {
    expect(prev({ slide: 2, step: 0 })).toEqual({ slide: 1, step: STEP_COUNTS[1] - 1 });
  });

  it("is a no-op at both ends", () => {
    const start = { slide: 0, step: 0 };
    expect(prev(start)).toBe(start);
    const end = { slide: SLIDE_COUNT - 1, step: STEP_COUNTS[SLIDE_COUNT - 1] - 1 };
    expect(next(end)).toBe(end);
  });

  it("jumps whole slides", () => {
    expect(nextSlide({ slide: 1, step: 1 })).toEqual({ slide: 2, step: 0 });
    expect(prevSlide({ slide: 0, step: 0 })).toEqual({ slide: 0, step: 0 });
  });

  it("round-trips the URL hash and clamps garbage", () => {
    expect(parseHash(toHash({ slide: 2, step: 2 }))).toEqual({ slide: 2, step: 2 });
    expect(parseHash("#/99/99")).toEqual({ slide: SLIDE_COUNT - 1, step: STEP_COUNTS[SLIDE_COUNT - 1] - 1 });
    expect(parseHash("nonsense")).toEqual({ slide: 0, step: 0 });
    expect(clampPos({ slide: -3, step: 77 })).toEqual({ slide: 0, step: STEP_COUNTS[0] - 1 });
  });

  it("global index is monotonic", () => {
    let p = { slide: 0, step: 0 };
    let last = -1;
    for (let i = 0; i < 40; i++) {
      const g = globalIndex(p);
      expect(g).toBeGreaterThanOrEqual(last);
      last = g;
      p = next(p);
    }
  });
});

import { SLIDES, TARGET_SECONDS } from "../data/notes";
describe("presenter notes", () => {
  it("have one note per step and a 3 minute budget", () => {
    SLIDES.forEach((s, i) => expect(s.notes.length).toBe(STEP_COUNTS[i]));
    expect(TARGET_SECONDS).toBe(180);
  });

  it("are speakable in the budget (≤ 2,6 words per second per slide)", () => {
    for (const s of SLIDES) {
      const words = s.notes.join(" ").split(/\s+/).filter(Boolean).length;
      expect(words / s.seconds, s.id).toBeLessThanOrEqual(2.6);
    }
  });
});
