import { useEffect, useRef, useState } from "react";

export const CANVAS_W = 1920;
export const CANVAS_H = 1080;

/** Scale that fits the 1920x1080 canvas inside the element, never clipping (letterboxed). */
export function useFit<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [fit, setFit] = useState({ scale: 1, w: CANVAS_W, h: CANVAS_H });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (w > 0 && h > 0) setFit({ scale: Math.min(w / CANVAS_W, h / CANVAS_H), w, h });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, ...fit };
}
