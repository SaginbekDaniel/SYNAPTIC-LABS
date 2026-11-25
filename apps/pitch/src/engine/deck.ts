/** Pure navigation model: a position is (slide, step). Steps are the reveal states inside one slide. */
export interface Pos { slide: number; step: number }

/** Reveal states per slide (see data/notes.ts for what each one shows). */
export const STEP_COUNTS = [1, 2, 3, 2, 3, 3, 2, 2] as const;
export const SLIDE_COUNT = STEP_COUNTS.length;
export const TOTAL_STEPS = STEP_COUNTS.reduce((a, b) => a + b, 0);

const lastStep = (slide: number) => STEP_COUNTS[slide] - 1;

export function clampPos(p: Pos): Pos {
  const slide = Math.min(Math.max(Math.trunc(p.slide) || 0, 0), SLIDE_COUNT - 1);
  const step = Math.min(Math.max(Math.trunc(p.step) || 0, 0), lastStep(slide));
  return { slide, step };
}

export function next(p: Pos): Pos {
  if (p.step < lastStep(p.slide)) return { slide: p.slide, step: p.step + 1 };
  if (p.slide < SLIDE_COUNT - 1) return { slide: p.slide + 1, step: 0 };
  return p;
}

/** Going back lands on the *completed* state of the previous slide, never on an empty one. */
export function prev(p: Pos): Pos {
  if (p.step > 0) return { slide: p.slide, step: p.step - 1 };
  if (p.slide > 0) return { slide: p.slide - 1, step: lastStep(p.slide - 1) };
  return p;
}

export function nextSlide(p: Pos): Pos {
  return p.slide < SLIDE_COUNT - 1 ? { slide: p.slide + 1, step: 0 } : p;
}
export function prevSlide(p: Pos): Pos {
  return p.slide > 0 ? { slide: p.slide - 1, step: 0 } : { slide: 0, step: 0 };
}

/** 0-based global index of a position, for progress display. */
export function globalIndex(p: Pos): number {
  let n = 0;
  for (let i = 0; i < p.slide; i++) n += STEP_COUNTS[i];
  return n + p.step;
}

/** Hash format: `#/3` (slide 3, step 1) or `#/3/5` (slide 3, step 5). Both 1-based for people. */
export function parseHash(hash: string): Pos {
  const m = /^#\/?(\d+)(?:\/(\d+))?$/.exec(hash);
  if (!m) return { slide: 0, step: 0 };
  return clampPos({ slide: Number(m[1]) - 1, step: m[2] ? Number(m[2]) - 1 : 0 });
}
export function toHash(p: Pos): string {
  return `#/${p.slide + 1}/${p.step + 1}`;
}
export const samePos = (a: Pos, b: Pos) => a.slide === b.slide && a.step === b.step;
