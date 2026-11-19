import { useCallback, useEffect, useRef, useState } from "react";
import { type Pos, clampPos, next, nextSlide, parseHash, prev, prevSlide, samePos, toHash } from "./deck";

/** Deck state synchronised with the URL hash so a refresh or a deep link is deterministic. */
export function useDeck() {
  const [pos, setPos] = useState<Pos>(() => parseHash(window.location.hash));
  const dir = useRef<1 | -1>(1);

  const go = useCallback((target: Pos | ((p: Pos) => Pos)) => {
    setPos((p) => {
      const t = clampPos(typeof target === "function" ? target(p) : target);
      if (samePos(t, p)) return p;
      dir.current = t.slide !== p.slide ? (t.slide > p.slide ? 1 : -1) : dir.current;
      return t;
    });
  }, []);

  useEffect(() => {
    const h = toHash(pos);
    if (window.location.hash !== h) window.history.replaceState(null, "", h);
  }, [pos]);

  useEffect(() => {
    const onHash = () => go(parseHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [go]);

  return {
    pos,
    direction: dir,
    go,
    next: useCallback(() => go(next), [go]),
    prev: useCallback(() => go(prev), [go]),
    nextSlide: useCallback(() => go(nextSlide), [go]),
    prevSlide: useCallback(() => go(prevSlide), [go]),
    restart: useCallback(() => go({ slide: 0, step: 0 }), [go]),
  };
}
