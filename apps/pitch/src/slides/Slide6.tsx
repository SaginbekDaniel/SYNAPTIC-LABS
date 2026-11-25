import { m } from "motion/react";
import { BENCH, dec } from "../data/bench";
import { CountUp, EASE, Head } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

interface Row {
  key: string;
  title: string;
  better: string;
  max: number;
  rules: { v: number; sub?: string };
  nexora: { v: number; sub?: string };
  unit: string;
}

const pctRow = (x: { n: number; of: number; pct: number }) => ({ v: x.pct, sub: `${x.n} из ${x.of}` });

/** Two measured advantages over per-account monitoring rules; both come from the committed holdout run. */
const ROWS: Row[] = [
  { key: "alerts", title: "Алертов на один набор данных", better: "меньше — лучше", max: 45, unit: "", rules: { v: BENCH.alertsPerDataset.rules }, nexora: { v: BENCH.alertsPerDataset.nexora } },
  { key: "legit", title: "Легитимных сетей попало в очередь", better: "меньше — лучше", max: 100, unit: " %", rules: pctRow(BENCH.legitFlagged.rules), nexora: pctRow(BENCH.legitFlagged.nexora) },
];

function Bar({ label, v, max, unit, sub, kind, delay }: { label: string; v: number; max: number; unit: string; sub?: string; kind: "rules" | "nexora"; delay: number }) {
  return (
    <div className={`s6-bar ${kind}`}>
      <span className="s6-who small">{label}</span>
      <div className="s6-track">
        <m.i initial={{ scaleX: 0 }} animate={{ scaleX: v / max }} transition={{ delay, duration: 0.9, ease: EASE }} />
      </div>
      <span className="s6-val num">{dec(v)}{unit}</span>
      <span className="s6-sub label">{sub ?? ""}</span>
    </div>
  );
}

export function Slide6({ step }: SlideProps) {
  return (
    <section className="slide s6" aria-labelledby="h-6">
      <Head index={6} />
      <div className="slide-body s6-body">
        <div className="s6-chart">
          {ROWS.map((r, i) => {
            const on = r.key === "alerts" || step >= 1;
            return (
              <m.div
                key={r.key} className="s6-row" data-row={r.key}
                initial={false} animate={{ opacity: on ? 1 : 0 }} transition={{ duration: 0.4 }} aria-hidden={!on}
              >
                <div className="s6-row-h">
                  <h3 className="h3">{r.title}</h3>
                  <span className="label">{r.better}</span>
                </div>
                {on && <>
                  <Bar label="Правила" kind="rules" v={r.rules.v} sub={r.rules.sub} max={r.max} unit={r.unit} delay={0.2 + i * 0.08} />
                  <Bar label="NEXORA" kind="nexora" v={r.nexora.v} sub={r.nexora.sub} max={r.max} unit={r.unit} delay={0.35 + i * 0.08} />
                </>}
              </m.div>
            );
          })}
        </div>

        <aside className="s6-side">
          <m.section
            className="s6-found" aria-label="Найдено подозрительных сетей" aria-hidden={step < 2}
            initial={false} animate={{ opacity: step >= 2 ? 1 : 0, y: step >= 2 ? 0 : 12 }} transition={{ duration: 0.5, ease: EASE }}
          >
            <h3 className="label caps">Найдено подозрительных сетей</h3>
            <p className="s6-found-n num"><CountUp to={BENCH.recall.nexora.pct} active={step >= 2} suffix=" %" /></p>
            <p className="small">{BENCH.recall.nexora.n} из {BENCH.recall.nexora.of} запланированных схем: воронки, веера, цепочки и циклы</p>
          </m.section>
          <section className="s6-method" aria-label="Методика">
            <h3 className="label caps">Как измеряли</h3>
            <dl>
              <div><dt className="num">{BENCH.datasets}</dt><dd className="small">наборов отложенной выборки</dd></div>
              <div><dt className="num">{BENCH.suspicious + BENCH.legitimate}</dt><dd className="small">сетей: {BENCH.suspicious} подозрительных, {BENCH.legitimate} легитимных</dd></div>
            </dl>
            <p className="label">Против правил по счёту · bench-v1, конфигурация v2 · коммит <span className="mono">{BENCH.commit}</span></p>
          </section>
        </aside>
      </div>
      <div className="slide-foot s6-foot">
        <span className="tag accent">Синтетические данные</span>
        <span className="label">Оценка на размеченных сценариях, воспроизводится одной командой. Не данные банка — это покажет офлайн-реплей.</span>
      </div>
    </section>
  );
}
