import { useLayoutEffect, useRef, useState } from "react";

/** Width of an element, tracked with one ResizeObserver; charts re-render only on real size changes. */
export function useElementWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(Math.round(el.getBoundingClientRect().width));
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.round(entry?.contentRect.width ?? 0);
      setWidth((prev) => (prev === w ? prev : w));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** Round tick step so that `count` steps cover v: 1, 2, 5 × 10^n (integers for counts). */
export function niceStep(v: number, count = 4): number {
  const raw = Math.max(1, v / count);
  const exp = Math.floor(Math.log10(raw));
  const base = 10 ** exp;
  for (const m of [1, 2, 5, 10]) if (m * base >= raw) return Math.max(1, m * base);
  return 10 * base;
}

/** Monotone cubic path (Fritsch–Carlson): smooth, never overshoots, so counts never dip below zero. */
export function monotonePath(pts: readonly [number, number][]): string {
  const n = pts.length;
  if (n === 0) return "";
  if (n === 1) return `M${r(pts[0]![0])},${r(pts[0]![1])}`;
  const dx: number[] = [];
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const h = pts[i + 1]![0] - pts[i]![0];
    dx.push(h);
    slope.push(h === 0 ? 0 : (pts[i + 1]![1] - pts[i]![1]) / h);
  }
  const m: number[] = [slope[0]!];
  for (let i = 1; i < n - 1; i++) {
    const a = slope[i - 1]!;
    const b = slope[i]!;
    m.push(a * b <= 0 ? 0 : (3 * (dx[i - 1]! + dx[i]!)) / ((2 * dx[i]! + dx[i - 1]!) / a + (dx[i]! + 2 * dx[i - 1]!) / b));
  }
  m.push(slope[n - 2]!);
  let d = `M${r(pts[0]![0])},${r(pts[0]![1])}`;
  for (let i = 0; i < n - 1; i++) {
    const [x0, y0] = pts[i]!;
    const [x1, y1] = pts[i + 1]!;
    const h = dx[i]! / 3;
    d += `C${r(x0 + h)},${r(y0 + m[i]! * h)},${r(x1 - h)},${r(y1 - m[i + 1]! * h)},${r(x1)},${r(y1)}`;
  }
  return d;
}

// Two decimals keep SVG paths short (rendering-svg-precision).
function r(v: number): number {
  return Math.round(v * 100) / 100;
}
