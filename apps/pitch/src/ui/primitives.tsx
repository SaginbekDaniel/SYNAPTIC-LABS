import { type ReactNode, useEffect, useState } from "react";
import { animate, m, useReducedMotion } from "motion/react";
import { SLIDES } from "../data/notes";

const EASE = [0.22, 1, 0.36, 1] as const;

/** Fade-up entrance. Under reduced motion the translate is dropped by MotionConfig; opacity remains. */
export function Reveal({ children, delay = 0, y = 28, className, style }: { children: ReactNode; delay?: number; y?: number; className?: string; style?: React.CSSProperties }) {
  return (
    <m.div className={className} style={style} initial={{ opacity: 0, y }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.75, ease: EASE }}>
      {children}
    </m.div>
  );
}

/** Shows children only while `when` is true, with a soft cross-fade. */
export function Fade({ when, children, className, delay = 0 }: { when: boolean; children: ReactNode; className?: string; delay?: number }) {
  return (
    <m.div className={className} initial={false} animate={{ opacity: when ? 1 : 0, y: when ? 0 : 12 }} transition={{ duration: 0.5, delay: when ? delay : 0, ease: EASE }} style={{ pointerEvents: when ? "auto" : "none" }} aria-hidden={!when}>
      {children}
    </m.div>
  );
}

/** Slide number + eyebrow; the eyebrow text comes from data/notes.ts (single source). */
export function SlideHeader({ index }: { index: number }) {
  const eyebrow = SLIDES[index - 1].eyebrow;
  return (
    <div className="eyebrow">
      <b>{String(index).padStart(2, "0")}</b>
      <i />
      <span>{eyebrow}</span>
    </div>
  );
}

/** Counts from `from` to `to` once `active`; renders Russian decimal comma. Deterministic end value. */
export function CountUp({ from = 0, to, active, decimals = 1, suffix = "", duration = 1.4 }: { from?: number; to: number; active: boolean; decimals?: number; suffix?: string; duration?: number }) {
  const reduced = useReducedMotion();
  const [v, setV] = useState(active ? (reduced ? to : from) : from);
  useEffect(() => {
    if (!active) {
      setV(from);
      return;
    }
    if (reduced) {
      setV(to);
      return;
    }
    const c = animate(from, to, { duration, ease: EASE, onUpdate: setV });
    return () => c.stop();
  }, [active, from, to, duration, reduced]);
  return <>{v.toFixed(decimals).replace(".", ",")}{suffix}</>;
}

/** Status glyphs always pair colour with a distinct shape (never colour alone). */
export function StatusIcon({ kind, size = 30 }: { kind: "supported" | "ambiguous" | "contradicted" | "unavailable"; size?: number }) {
  const c = { supported: "var(--ok)", ambiguous: "var(--warn)", contradicted: "var(--risk)", unavailable: "var(--text-3)" }[kind];
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flex: "none" }}>
      <circle cx="12" cy="12" r="10" strokeDasharray={kind === "unavailable" ? "2 3.5" : undefined} />
      {kind === "supported" && <path d="M7.5 12.5l3 3 6-7" />}
      {kind === "ambiguous" && <path d="M7.5 12h9" />}
      {kind === "contradicted" && <path d="M8.5 8.5l7 7M15.5 8.5l-7 7" />}
      {kind === "unavailable" && <path d="M12 8v.01M12 11.5v4.5" />}
    </svg>
  );
}

export function Icon({ name }: { name: "prev" | "next" | "grid" | "notes" | "full" | "exit" | "restart" | "help" | "play" | "pause" | "close" }) {
  const p: Record<string, string> = {
    prev: "M15 5l-7 7 7 7",
    next: "M9 5l7 7-7 7",
    grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
    notes: "M6 3h9l4 4v14H6zM9 12h7M9 16h7M9 8h3",
    full: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
    exit: "M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5",
    restart: "M4 12a8 8 0 1 0 3-6.2M4 4v5h5",
    help: "M9.5 9a2.5 2.5 0 1 1 3.6 2.2c-.8.5-1.1 1-1.1 1.8M12 17v.01",
    play: "M8 5l11 7-11 7z",
    pause: "M8 5v14M16 5v14",
    close: "M6 6l12 12M18 6L6 18",
  };
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={p[name]} />
      {name === "help" && <circle cx="12" cy="12" r="9" />}
    </svg>
  );
}
