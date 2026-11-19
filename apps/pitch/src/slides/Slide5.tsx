import { m } from "motion/react";
import { BENCH, FAMILIES, WORKLOAD_CUT, WORKLOAD_RATIO, dec, type Family } from "../data/bench";
import { METRICS } from "../data/results";
import { CountUp, Fade, Reveal, SlideHeader } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * One dot per synthetic scenario. A filled dot = the method put that scenario in the analyst's queue.
 * For legitimate families a filled dot is a false alarm (risk), for suspicious ones it is a catch (ok).
 * A ring = NEXORA showed it as "insufficient evidence" instead of raising it. Shape, not colour alone.
 */
function Dots({ f, n, ring = 0, active }: { f: Family; n: number; ring?: number; active: boolean }) {
  const tone = f.kind === "legit" ? "risk" : "ok";
  return (
    <span className="dots" aria-hidden="true">
      {Array.from({ length: f.total }, (_, i) => {
        const cls = i < n ? `dot fill ${tone}` : i < n + ring ? "dot ring" : "dot";
        return <m.i key={i} className={cls} initial={false} animate={{ opacity: active ? 1 : 0.18, scale: active ? 1 : 0.6 }} transition={{ duration: 0.35, delay: active ? i * 0.012 : 0, ease: EASE }} />;
      })}
    </span>
  );
}

function Group({ kind, title, active }: { kind: Family["kind"]; title: string; active: boolean }) {
  const rows = FAMILIES.filter((f) => f.kind === kind);
  return (
    <div className={`atlas-group ${active ? "on" : ""}`} role="rowgroup">
      <div className={`atlas-gh ${kind}`} role="row"><span role="rowheader">{title}</span></div>
      {rows.map((f) => (
        <div className="atlas-row" key={f.id} role="row">
          <span className="atlas-name" role="rowheader">{f.label}</span>
          <span role="cell" aria-label={`Правила: ${f.rules} из ${f.total}`}><Dots f={f} n={f.rules} active={active} /></span>
          <span role="cell" aria-label={`NEXORA: ${f.nexora} из ${f.total}${f.nexoraSurfaced > f.nexora ? `, ещё ${f.nexoraSurfaced - f.nexora} — «недостаточно данных»` : ""}`}>
            <Dots f={f} n={f.nexora} ring={f.nexoraSurfaced - f.nexora} active={active} />
          </span>
        </div>
      ))}
    </div>
  );
}

function Kpi({ when, label, from, to, unit, note, good }: { when: boolean; label: string; from: number; to: number; unit: string; note: string; good: boolean }) {
  return (
    <Fade when={when} className="kpi">
      <span className="label up">{label}</span>
      <div className="kpi-num mono">
        <span className="from">{dec(from)}{unit}</span>
        <span className="arrow" aria-hidden="true">→</span>
        <b className={good ? "good" : "cost"}><CountUp from={from} to={to} active={when} suffix={unit} /></b>
      </div>
      <p className="small">{note}</p>
    </Fade>
  );
}

export function Slide5({ step }: SlideProps) {
  const on = (i: number) => step >= i;
  const sealedFpr = METRICS[0];
  return (
    <section className="slide" aria-labelledby="h-5">
      <Reveal><SlideHeader index={5} /></Reveal>
      <div className="slide-inner s5">
        <Reveal delay={0.1}><h2 id="h-5" className="h1 s5-title">Тревог в {dec(WORKLOAD_RATIO)} раза меньше, <span className="grad">чем у правил мониторинга</span></h2></Reveal>

        <div className="s5-grid">
          <div className="glass atlas" role="table" aria-label="Каждая точка — синтетический сценарий; закрашенная — попал в очередь аналитика">
            <div className="atlas-row atlas-head" role="row">
              <span role="columnheader">{BENCH.datasets} наборов · {BENCH.legitimate + BENCH.suspicious} сценариев</span>
              <span role="columnheader">Правила мониторинга</span>
              <span role="columnheader" className="nx">NEXORA</span>
            </div>
            <Group kind="legit" title={`Легитимные двойники · ${BENCH.legitimate}`} active={on(0)} />
            <Group kind="suspicious" title={`Подозрительные сети · ${BENCH.suspicious}`} active={on(1)} />
            <div className="atlas-legend" aria-hidden="true">
              <span><i className="dot fill risk" />ложная тревога</span>
              <span><i className="dot fill ok" />сеть найдена</span>
              <span><i className="dot ring" />«недостаточно данных»</span>
              <span><i className="dot" />не в очереди</span>
            </div>
          </div>

          <div className="s5-side">
            <Kpi when={on(0)} label="Алертов на набор данных" from={BENCH.alertsPerDataset.rules} to={BENCH.alertsPerDataset.nexora} unit="" good
              note={`Очередь короче на ${WORKLOAD_CUT} %. Легитимных сетей в ней: ${dec(BENCH.fpr.rules)} → ${dec(BENCH.fpr.nexora)} %`} />
            <Kpi when={on(1)} label="Найдено подозрительных сетей" from={BENCH.recall.rules} to={BENCH.recall.nexora} unit=" %" good={false}
              note={`Цена сдержанности. С пометкой «недостаточно данных» — ${dec(BENCH.surfacedRecall)} %`} />
            <Kpi when={on(2)} label="Реальные сети в первых пяти" from={BENCH.p5.rules} to={BENCH.p5.nexora} unit=" %" good
              note={`В высоком приоритете легитимных сетей ${dec(BENCH.highBandFpr)} %`} />
          </div>
        </div>

        <div className="s5-foot">
          <div className="disclaimer" role="note">
            <span className="chip warn">Важно</span>
            <b>Синтетические данные команды — это не точность на данных банка</b>
          </div>
          <Fade when={on(3)} className="s5-next">
            <span className="chip violet">В разработке</span>
            <span className="small">Следующая версия движка, закрытая выборка: ложные {dec(sealedFpr.before)} % → {dec(sealedFpr.after)} %, полнота не ниже</span>
          </Fade>
        </div>
      </div>
    </section>
  );
}
