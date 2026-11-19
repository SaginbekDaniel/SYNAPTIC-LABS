import { useEffect, useMemo, useState } from "react";
import { Network, type EdgeSpec, type NodeSpec, type Tone } from "../ui/Network";
import { Fade, Reveal, SlideHeader } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const W = 960, H = 880;

type Pt = [number, number];
const ACCT: Record<string, { p: Pt; role: "funnel" | "hubr" | "out" | "chain" | "cycle" }> = {
  F1: { p: [80, 130], role: "funnel" }, F2: { p: [80, 245], role: "funnel" }, F3: { p: [80, 360], role: "funnel" }, F4: { p: [80, 475], role: "funnel" },
  H: { p: [340, 300], role: "hubr" },
  O1: { p: [580, 190], role: "out" }, O2: { p: [580, 410], role: "out" },
  C1: { p: [770, 110], role: "chain" }, C2: { p: [880, 270], role: "chain" },
  R1: { p: [640, 600], role: "cycle" }, R2: { p: [860, 660], role: "cycle" }, R3: { p: [700, 820], role: "cycle" },
};
// id, from, to, group
const TRANSFERS: [string, string, string, "funnel" | "chain" | "cycle"][] = [
  ["t1", "F1", "H", "funnel"], ["t2", "F2", "H", "funnel"], ["t3", "F3", "H", "funnel"], ["t4", "F4", "H", "funnel"],
  ["t5", "H", "O1", "funnel"], ["t6", "H", "O2", "funnel"],
  ["t7", "O1", "C1", "chain"], ["t8", "C1", "C2", "chain"],
  ["t9", "O2", "R1", "cycle"], ["t10", "R1", "R2", "cycle"], ["t11", "R2", "R3", "cycle"], ["t12", "R3", "R1", "cycle"],
];
// scattered layout: pair centre (4x3 grid, hand-jittered) + angle + length; deterministic, no randomness
const CELL: [number, number, number, number][] = [
  [120, 150, 20, 120], [370, 110, -35, 100], [610, 180, 70, 110], [850, 120, 15, 100],
  [100, 450, -60, 110], [350, 420, 30, 130], [600, 470, -15, 100], [850, 400, 55, 120],
  [140, 770, 10, 110], [390, 740, -45, 120], [630, 800, 25, 100], [850, 770, -70, 110],
];

const TONE_BY_ROLE: Record<string, Tone> = { funnel: "source", hubr: "hub", out: "sink", chain: "warn", cycle: "risk" };
const EDGE_TONE: Record<string, Tone> = { funnel: "hub", chain: "warn", cycle: "risk" };

function build(step: number, lens: "net" | "tx") {
  const merged = step >= 1;
  const colored = step >= 2 && lens === "net";
  const nodes: NodeSpec[] = [];
  const edges: EdgeSpec[] = [];
  TRANSFERS.forEach(([id, from, to, group], i) => {
    const [cx, cy, deg, len] = CELL[i];
    const a = (deg * Math.PI) / 180;
    const sa: Pt = [cx - (Math.cos(a) * len) / 2, cy - (Math.sin(a) * len) / 2];
    const sb: Pt = [cx + (Math.cos(a) * len) / 2, cy + (Math.sin(a) * len) / 2];
    const fa = ACCT[from], fb = ACCT[to];
    const toneA: Tone = colored ? TONE_BY_ROLE[fa.role] : "neutral";
    const toneB: Tone = colored ? TONE_BY_ROLE[fb.role] : "neutral";
    const hubby = (r: string) => r === "hubr";
    nodes.push({ id: `${id}a`, x: merged ? fa.p[0] : sa[0], y: merged ? fa.p[1] : sa[1], tone: toneA, r: hubby(fa.role) && merged ? 20 : 11, pulse: colored && hubby(fa.role) });
    nodes.push({ id: `${id}b`, x: merged ? fb.p[0] : sb[0], y: merged ? fb.p[1] : sb[1], tone: toneB, r: hubby(fb.role) && merged ? 20 : 11, pulse: colored && hubby(fb.role) });
    edges.push({
      id, from: `${id}a`, to: `${id}b`, flow: true,
      tone: colored ? EDGE_TONE[group] : "neutral",
      width: colored ? 4 : 3,
      className: step >= 2 && lens === "tx" ? "scanning" : undefined,
      scanDelay: i * 0.4,
    });
  });
  return { nodes, edges };
}

const CAPTIONS = [
  "12 отдельных переводов. Сумма, дата, два счёта — ничего необычного.",
  "У переводов общие счета. Отдельные платежи складываются в сеть.",
  "Воронка, цепочка и цикл существуют только на уровне сети.",
  "Проверка по одному переводу не видит поведения сети.",
];

export function Slide1({ step }: SlideProps) {
  const [override, setOverride] = useState<"net" | "tx" | null>(null);
  useEffect(() => setOverride(null), [step]);
  const lens: "net" | "tx" = override ?? (step === 3 ? "tx" : "net");
  const { nodes, edges } = useMemo(() => build(step, lens), [step, lens]);
  const showPatterns = step >= 2 && lens === "net";

  return (
    <section className="slide" aria-labelledby="h-1">
      <Reveal><SlideHeader index={1} eyebrow="The problem" /></Reveal>
      <div className="slide-inner s1">
        <div className="s1-left">
          <Reveal delay={0.1}>
            <h2 id="h-1" className="h1 s1-title">Мошенничество <span className="grad">скрывается в связях</span></h2>
          </Reveal>
          <ol className="s1-steps" aria-label="Ход рассказа">
            {CAPTIONS.map((c, i) => (
              <li key={i} className={i === step ? "on" : i < step ? "past" : ""} aria-current={i === step ? "step" : undefined}>
                <span className="mono">{i + 1}</span>
                <p>{c}</p>
              </li>
            ))}
          </ol>
          <Fade when={step >= 2} className="s1-lens">
            <span className="label">Взгляд на те же данные</span>
            <div className="seg" role="group" aria-label="Взгляд на данные">
              <button className="btn" aria-pressed={lens === "tx"} onClick={() => setOverride("tx")}>По одному переводу</button>
              <button className="btn" aria-pressed={lens === "net"} onClick={() => setOverride("net")}>По сети</button>
            </div>
          </Fade>
        </div>

        <div className="s1-graph" style={{ width: W, height: H }}>
          <Network width={W} height={H} nodes={nodes} edges={edges} duration={1.6} label="Переводы между счетами: сначала разрозненные, затем связанные в сеть" />
          <Fade when={showPatterns} className="pat" delay={0.5}><span className="chip violet" style={{ left: 40, top: 56 }}>Воронка сбора</span></Fade>
          <Fade when={showPatterns} className="pat" delay={0.7}><span className="chip warn" style={{ left: 690, top: 56 }}>Цепочка</span></Fade>
          <Fade when={showPatterns} className="pat" delay={0.9}><span className="chip risk" style={{ left: 380, top: 790 }}>Круговой поток</span></Fade>
          <Fade when={step >= 2 && lens === "tx"} className="pat tx-note">
            <span className="chip">Каждый перевод по отдельности: обычный платёж</span>
          </Fade>
        </div>
      </div>
      <Reveal delay={0.3} className="s1-tag"><span className="chip cyan">Иллюстрация на синтетических данных</span></Reveal>
    </section>
  );
}
