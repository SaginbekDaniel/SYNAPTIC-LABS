import { m } from "motion/react";
import { Fade, Reveal, SlideHeader } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const EASE = [0.22, 1, 0.36, 1] as const;

/** What changes for each role in the bank. Only properties the prototype already has; no projected savings. */
const ROLES = [
  {
    who: "Аналитик антифрода и AML",
    points: ["Очередь сетей вместо россыпи отдельных алертов", "Каждый вывод — со ссылкой на переводы-источники", "Явно сказано, чего система не знает"],
  },
  {
    who: "Комплаенс и риск",
    points: ["Детерминированные правила, без генеративного ИИ в доказательствах: результат воспроизводим", "Решение и обоснование — в журнале только на добавление", "Никаких автоматических действий против клиентов"],
  },
  {
    who: "ИТ и информационная безопасность",
    points: ["Работает на выгрузке переводов, без доступа к АБС", "Python, PostgreSQL, React, Docker — развёрнут в облаке", "Суммы и идентификаторы без потери точности"],
  },
];

const STAGES = [
  { n: "01", name: "Офлайн-реплей", text: "Обезличенная история переводов и закрытые кейсы банка. Первая честная оценка на реальных данных." },
  { n: "02", name: "Теневой режим", text: "Рядом с текущим мониторингом, без влияния на клиентов. Сравниваем очереди и время разбора." },
  { n: "03", name: "Аналитик в контуре", text: "NEXORA формирует очередь, решение остаётся за аналитиком, каждое действие — в журнале." },
];

const NEEDS = ["Обезличенная выгрузка переводов", "Разметка закрытых расследований", "Атрибуты KYC и MCC — чтобы отличать легитимных двойников", "Согласование контура с ИБ"];

export function Slide6({ step }: SlideProps) {
  return (
    <section className="slide" aria-labelledby="h-6">
      <Reveal><SlideHeader index={6} /></Reveal>
      <div className="slide-inner s6p">
        <Reveal delay={0.1}><h2 id="h-6" className="h1 s6p-title">Что получает банк <span className="grad">и как дойти до пилота</span></h2></Reveal>

        <ul className="roles">
          {ROLES.map((r, i) => (
            <m.li key={r.who} className="glass role" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 + i * 0.12, duration: 0.6, ease: EASE }}>
              <h3 className="h3">{r.who}</h3>
              <ul>{r.points.map((p) => <li key={p}>{p}</li>)}</ul>
            </m.li>
          ))}
        </ul>

        <Fade when={step >= 1} className="pilot">
          <ol className="stages" aria-label="Этапы пилота">
            {STAGES.map((s, i) => (
              <m.li key={s.n} initial={false} animate={{ opacity: step >= 1 ? 1 : 0, x: step >= 1 ? 0 : -20 }} transition={{ delay: step >= 1 ? 0.15 + i * 0.15 : 0, duration: 0.55, ease: EASE }}>
                <span className="mono">{s.n}</span>
                <b>{s.name}</b>
                <p>{s.text}</p>
              </m.li>
            ))}
          </ol>
          <div className="needs">
            <span className="label up">Что нужно от банка</span>
            <ul>{NEEDS.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        </Fade>
      </div>
    </section>
  );
}
