import { useMemo } from "react";
import { m, useReducedMotion } from "motion/react";
import { Reveal, SlideHeader } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const W = 1920, H = 1080;

/** Deterministic pseudo-random (LCG) so the background is identical on every load. */
function field() {
  let s = 20261118;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const nodes = Array.from({ length: 44 }, () => ({ x: rnd() * W, y: rnd() * H, r: 3 + rnd() * 4 }));
  const edges: [number, number][] = [];
  nodes.forEach((a, i) => {
    nodes
      .map((b, j) => ({ j, d: Math.hypot(a.x - b.x, a.y - b.y) }))
      .filter((o) => o.j > i && o.d < 330)
      .sort((p, q) => p.d - q.d)
      .slice(0, 2)
      .forEach((o) => edges.push([i, o.j]));
  });
  return { nodes, edges };
}

const PILLARS = ["Объяснимость", "Доказательства", "Решение аналитика"];

export function Slide6(props: SlideProps) {
  void props;
  const reduced = useReducedMotion();
  const { nodes, edges } = useMemo(field, []);
  const pulses = edges.filter((_, i) => i % 6 === 0).slice(0, 8);

  return (
    <section className="slide s6" aria-labelledby="h-6">
      <svg className="s6-bg" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
        <g className="drift">
          {edges.map(([a, b], i) => (
            <line key={i} x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y} stroke="rgb(165 139 245 / 0.16)" strokeWidth="1.5" />
          ))}
          {nodes.map((n, i) => (
            <circle key={i} cx={n.x} cy={n.y} r={n.r} fill={i % 5 === 0 ? "var(--cyan)" : "var(--violet)"} opacity="0.55" />
          ))}
          {!reduced && pulses.map(([a, b], i) => (
            <m.circle
              key={i} r="5" fill="var(--cyan)"
              initial={{ cx: nodes[a].x, cy: nodes[a].y, opacity: 0 }}
              animate={{ cx: [nodes[a].x, nodes[b].x], cy: [nodes[a].y, nodes[b].y], opacity: [0, 1, 1, 0] }}
              transition={{ duration: 3.2, delay: i * 0.55, repeat: Infinity, repeatDelay: 1.5, ease: "linear" }}
            />
          ))}
        </g>
      </svg>

      <Reveal><SlideHeader index={6} eyebrow="The finale" /></Reveal>
      <div className="slide-inner s6-inner">
        <div className="wm-wrap">
          <span className="wm wm-glow" aria-hidden="true">NEXORA&nbsp;AI</span>
          <m.h2
            id="h-6" className="wm wm-main"
            aria-label="NEXORA AI"
            initial={{ clipPath: "inset(0 100% 0 0)", scale: 1.04 }} animate={{ clipPath: "inset(0 0% 0 0)", scale: 1 }}
            transition={{ duration: 1.5, ease: [0.22, 1, 0.36, 1] }}
          >
            NEXORA&nbsp;AI
          </m.h2>
        </div>
        <Reveal delay={0.9}><p className="s6-head">От подозрения — к проверяемому расследованию</p></Reveal>
        <ul className="pillars" aria-label="Три опоры">
          {PILLARS.map((p, i) => (
            <m.li key={p} className="glass" initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.2 + i * 0.18, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
              <span className="mono">{String(i + 1).padStart(2, "0")}</span>{p}
            </m.li>
          ))}
        </ul>
        <Reveal delay={1.9}><p className="label s6-note">Прототип на синтетических данных · без интеграции с банком · SYNAPTIC LABS · ITU Hackathon 2026</p></Reveal>
      </div>
    </section>
  );
}
