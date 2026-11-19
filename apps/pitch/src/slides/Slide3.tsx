import { m } from "motion/react";
import { FUNNEL_DAYS, FUNNEL_EDGES, FUNNEL_FACTS as F, FUNNEL_NODES } from "../data/funnel";
import { dec } from "../data/bench";
import { Graph } from "../ui/Graph";
import { EASE, Head, Reveal, StatusIcon } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

/** Four structural shapes the detectors look for (glyphs in a 64×48 box). */
const SHAPES: { name: string; d: string; dots: [number, number][] }[] = [
  { name: "Воронка", d: "M6 6L32 24M6 24L32 24M6 42L32 24M32 24L58 24", dots: [[6, 6], [6, 24], [6, 42], [32, 24], [58, 24]] },
  { name: "Веер", d: "M6 24L32 24M32 24L58 6M32 24L58 24M32 24L58 42", dots: [[6, 24], [32, 24], [58, 6], [58, 24], [58, 42]] },
  { name: "Цепочка", d: "M6 24L23 24M23 24L41 24M41 24L58 24", dots: [[6, 24], [23, 24], [41, 24], [58, 24]] },
  { name: "Цикл", d: "M32 6L56 40M56 40L8 40M8 40L32 6", dots: [[32, 6], [56, 40], [8, 40]] },
];

function Shapes() {
  return (
    <ul className="s3-shapes" aria-label="Формы, которые ищут детекторы">
      {SHAPES.map((s, i) => (
        <li key={s.name} className={i === 0 ? "on" : ""}>
          <svg viewBox="0 0 64 48" aria-hidden="true">
            <path d={s.d} />
            {s.dots.map(([x, y], k) => <circle key={k} cx={x} cy={y} r="4.5" />)}
          </svg>
          <span>{s.name}</span>
        </li>
      ))}
    </ul>
  );
}

function Timeline() {
  const max = Math.max(...FUNNEL_DAYS.map((d) => Math.max(d.inK, d.outK)));
  return (
    <div className="s3-time" role="img" aria-label="Поступления 12–14 июля, вывод 17 июля">
      {FUNNEL_DAYS.map((d) => (
        <div key={d.day} className="s3-day">
          <div className="s3-bars">
            {d.inK > 0 && <i className="in" style={{ height: `${(d.inK / max) * 100}%` }} />}
            {d.outK > 0 && <i className="out" style={{ height: `${(d.outK / max) * 100}%` }} />}
          </div>
          <span className="mono">{d.day}</span>
        </div>
      ))}
    </div>
  );
}

function Peers() {
  const x = (v: number) => `${v}%`;
  return (
    <div className="s3-peer" role="img" aria-label={`Доля оборота за 3 дня: счёт ${dec(F.peerShare)} %, медиана ${dec(F.peerMedian)} %, порог выброса ${dec(F.peerFence)} %`}>
      <div className="s3-scale-l">
        <span className="med" style={{ left: x(F.peerMedian) }}>медиана {dec(F.peerMedian)}</span>
        <span className="fence" style={{ left: x(F.peerFence) }}>выброс &gt; {dec(F.peerFence)}</span>
        <span className="me" style={{ left: x(F.peerShare) }}>этот счёт {dec(F.peerShare)} %</span>
      </div>
      <div className="s3-scale">
        <i className="zone" style={{ left: x(F.peerFence), right: 0 }} />
        <b className="tick med" style={{ left: x(F.peerMedian) }} />
        <b className="tick fence" style={{ left: x(F.peerFence) }} />
        <b className="dot" style={{ left: x(F.peerShare) }} />
      </div>
    </div>
  );
}

const TESTS = [
  { k: "structure", title: "Структура", text: "Детекторы ищут четыре формы. Здесь — воронка 5 → 1 → 2", viz: <Shapes />, verdict: <span className="tag">Где смотреть</span> },
  { k: "time", title: "Хронология", text: `${F.temporalShare} поступлений 12–14 июля могли профинансировать вывод 17 июля`, viz: <Timeline />, verdict: <span className="tag ok"><StatusIcon kind="supported" size={24} /> Подтверждает</span> },
  { k: "peers", title: "Похожие счета", text: `Доля оборота за 3 дня против ${F.peerCohort} счетов похожей активности: выше медианы, но не выброс`, viz: <Peers />, verdict: <span className="tag"><StatusIcon kind="unavailable" size={24} /> Без вывода</span> },
];

/** Method: shape → chronology → peer context, on the same funnel. Each step reveals one test. */
export function Slide3({ step }: SlideProps) {
  return (
    <section className="slide s3" aria-labelledby="h-3">
      <Head index={3} />
      <div className="slide-body s3-body">
        <Reveal delay={0.1} className="s3-graph">
          <Graph
            nodes={FUNNEL_NODES} edges={FUNNEL_EDGES} byDay
            edgeLabel={step >= 1 ? (e) => `${e.day}.07` : undefined}
            title="Воронка ··7530: пять входящих переводов 12–14 июля, два исходящих 17 июля"
          />
        </Reveal>
        <ol className="s3-tests">
          {TESTS.map((t, i) => {
            const on = step >= i;
            return (
              <m.li
                key={t.k} className={step === i ? "cur" : ""}
                initial={false} animate={{ opacity: on ? 1 : 0, y: on ? 0 : 16 }}
                transition={{ duration: 0.5, delay: on ? 0.15 : 0, ease: EASE }}
                aria-hidden={!on}
              >
                <div className="s3-row">
                  <span className="s3-n mono">{i + 1}</span>
                  <h3 className="h3">{t.title}</h3>
                  {t.verdict}
                </div>
                <p className="small s3-text">{t.text}</p>
                <div className="s3-viz">{t.viz}</div>
              </m.li>
            );
          })}
        </ol>
      </div>
      <m.div className="slide-foot" initial={false} animate={{ opacity: step >= 2 ? 1 : 0 }} transition={{ duration: 0.5, delay: step >= 2 ? 0.5 : 0 }} aria-hidden={step < 2}>
        <p className="body t-1">Итог в продукте: приоритет <b className="num">{F.priority}</b> из 100 — очерёдность проверки, а не вероятность мошенничества.</p>
      </m.div>
    </section>
  );
}
