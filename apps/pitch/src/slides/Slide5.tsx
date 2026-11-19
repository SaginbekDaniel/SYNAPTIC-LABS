import { useState } from "react";
import { m } from "motion/react";
import { METRICS, META, num, signed, type Metric } from "../data/results";
import { CountUp, Fade, Reveal, SlideHeader } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const EASE = [0.22, 1, 0.36, 1] as const;

/** Paired before/after bars on a shared 0–100 % axis (honest baseline: bars start at zero). */
function Bars({ m: metric, active, big }: { m: Metric; active: boolean; big?: boolean }) {
  const good = metric.lowerIsBetter ? metric.after < metric.before : metric.after > metric.before;
  return (
    <div className={`bars ${big ? "big" : ""}`}>
      <div className="brow">
        <span className="bl">v2 (в main)</span>
        <div className="track"><m.i className="fill base" initial={false} animate={{ width: active ? `${metric.before}%` : "0%" }} transition={{ duration: 1.1, ease: EASE }} /></div>
        <b className="bv mono"><CountUp to={metric.before} active={active} suffix=" %" /></b>
      </div>
      <div className="brow">
        <span className="bl">Кандидат</span>
        <div className="track"><m.i className={`fill ${good ? "good" : "flat"}`} initial={false} animate={{ width: active ? `${metric.after}%` : "0%" }} transition={{ duration: 1.3, delay: 0.35, ease: EASE }} /></div>
        <b className="bv mono now"><CountUp to={metric.after} active={active} suffix=" %" duration={1.6} /></b>
      </div>
    </div>
  );
}

export function Slide5({ step }: SlideProps) {
  const [limits, setLimits] = useState(false);
  const [fpr, rec, p5, hb] = METRICS;
  const on = (i: number) => step >= i;
  return (
    <section className="slide" aria-labelledby="h-5">
      <Reveal><SlideHeader index={5} eyebrow="Verified results" /></Reveal>
      <div className="slide-inner s5">
        <Reveal delay={0.1}><h2 id="h-5" className="h1 s5-title">Меньше ложных тревог. <span className="grad">Больше полезных проверок</span></h2></Reveal>

        <div className="s5-grid">
          <m.div className="glass hero" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.7, ease: EASE }}>
            <span className="label up">{fpr.title}</span>
            <div className="bignum mono">
              <span className="from">{num(fpr.before)}%</span>
              <span className="arrow" aria-hidden="true">→</span>
              <span className="to"><CountUp to={fpr.after} active={on(0)} suffix="%" duration={1.8} /></span>
            </div>
            <Bars m={fpr} active={on(0)} big />
            <p className="small">{fpr.hint}. Разница {signed(fpr.delta)} п.п., 95 % интервал [{signed(fpr.ci[0])}; {signed(fpr.ci[1])}].</p>
          </m.div>

          <div className="trio">
            {[rec, p5, hb].map((m, i) => (
              <Fade key={m.key} when={on(i + 1)} className="glass card">
                <div className="chead"><span className="h3">{m.title}</span><span className={`chip ${m.key === "recall" ? "" : "ok"}`}>{signed(m.delta)} п.п.</span></div>
                <Bars m={m} active={on(i + 1)} />
                <p className="label">95 % интервал [{signed(m.ci[0])}; {signed(m.ci[1])}]{m.key === "recall" ? " — «не хуже», а не «лучше»" : ""}</p>
              </Fade>
            ))}
          </div>
        </div>

        <div className="s5-foot">
          <div className="disclaimer" role="note">
            <span className="chip warn">Важно</span>
            <b>Синтетический benchmark, {META.datasets} датасетов. Не оценка точности на реальных данных банка</b>
          </div>
          <div className="s5-meta">
            <span className="chip">sealed-v1 · оценён один раз · исход: улучшение</span>
            <span className="chip warn">Артефакт в PR №3 · ещё не в main</span>
            <button className="btn" aria-pressed={limits} onClick={() => setLimits((v) => !v)}>Что не решено</button>
          </div>
          {limits && (
            <m.p className="small limits" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              Без KYC и данных мерчантов неотличимы от схемы: продажа билетов (22 из 23 всё ещё помечены), благотворительные сборы (13 из 36), денежные переводы семьи (5 из 20). Повторяющиеся «мулы» пропущены в обеих версиях (1 из 8).
            </m.p>
          )}
        </div>
      </div>
    </section>
  );
}
