import { m } from "motion/react";
import { DEMO_URL, REPO_URL, host } from "../data/links";
import { QR } from "../data/qr";
import { EASE, Head, Reveal } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const STAGES = [
  { t: "Офлайн-реплей", d: "Обезличенная история переводов и закрытые кейсы. Первая честная оценка на реальных данных.", now: true },
  { t: "Теневой режим", d: "Рядом с текущим мониторингом, без влияния на клиентов. Сравниваем очереди." },
  { t: "Аналитик в контуре", d: "NEXORA формирует очередь, решение за аналитиком, каждое действие — в журнале." },
];

const NEEDS = [
  "Обезличенная выгрузка переводов",
  "Разметка закрытых расследований",
  "Атрибуты KYC и MCC — чтобы отличать легитимных «двойников»",
  "Согласование контура с информационной безопасностью",
];

/** Pilot path and the ask; second state closes with the links. No timelines, savings or accuracy are promised. */
export function Slide7({ step }: SlideProps) {
  const close = step >= 1;
  return (
    <section className="slide s7" aria-labelledby="h-7">
      <Head index={7} />
      <div className="slide-body s7-body">
        <ol className="s7-path" aria-label="Этапы пилота">
          {STAGES.map((s, i) => (
            <m.li key={s.t} className={s.now ? "now" : ""} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.1, duration: 0.5, ease: EASE }}>
              <div className="s7-step"><span className="mono">{String(i + 1).padStart(2, "0")}</span>{s.now && <span className="tag accent">Предлагаем сейчас</span>}</div>
              <h3 className="h2">{s.t}</h3>
              <p className="small">{s.d}</p>
            </m.li>
          ))}
        </ol>
        <div className="s7-low">
          <Reveal delay={0.5} className="s7-needs">
            <h3 className="label caps">Что нужно от банка</h3>
            <ul>{NEEDS.map((n) => <li key={n} className="small t-1">{n}</li>)}</ul>
          </Reveal>
          <m.div className="s7-links" initial={false} animate={{ opacity: close ? 1 : 0, x: close ? 0 : 16 }} transition={{ duration: 0.5, ease: EASE }} aria-hidden={!close}>
            <svg className="qr" viewBox={`-2 -2 ${QR.size + 4} ${QR.size + 4}`} role="img" aria-label="QR-код: репозиторий проекта на GitHub" shapeRendering="crispEdges">
              <rect x="-2" y="-2" width={QR.size + 4} height={QR.size + 4} fill="#fff" />
              <path d={QR.path} fill="#090a0f" />
            </svg>
            <div className="s7-urls">
              <span className="label">Код и документация</span>
              <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className="mono" tabIndex={close ? 0 : -1}>{host(REPO_URL)}</a>
              <span className="label">Живое демо · доступ по запросу жюри</span>
              <a href={DEMO_URL} target="_blank" rel="noopener noreferrer" className="mono" tabIndex={close ? 0 : -1}>{host(DEMO_URL)}</a>
            </div>
          </m.div>
        </div>
      </div>
      <div className="slide-foot">
        <span className="label">Сроки, экономию и точность не обещаем до первого шага. Прототип на синтетических данных, без интеграции с банком. SYNAPTIC LABS</span>
      </div>
    </section>
  );
}
