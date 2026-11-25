import { m } from "motion/react";
import { EASE, Head } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

/** The real pipeline (docs/ARCHITECTURE.md, README "How it works"), condensed to six stages. */
const STAGES = [
  { t: "Импорт", d: "CSV или генератор. Битые строки — в карантин, дубли отсекаются" },
  { t: "Граф", d: "Счета — узлы, переводы — рёбра. Суммы в целых единицах" },
  { t: "Детекторы", d: "Воронка, веер, цепочка, цикл — кандидаты для проверки" },
  { t: "Сигналы", d: "Хронология потока, похожие счета, границы данных" },
  { t: "Доказательства", d: "Каждая цифра пересчитывается из исходных транзакций" },
  { t: "Решение", d: "Очередь по приоритету, решение аналитика, журнал аудита" },
];

const RULES = [
  { t: "Без генеративного ИИ", d: "Доказательства строят детерминированные алгоритмы, не языковая модель" },
  { t: "Воспроизводимо", d: "Повторный анализ тех же данных даёт тот же результат и те же идентификаторы" },
  { t: "Решает человек", d: "Система не блокирует счета и ничего не отправляет клиентам" },
];

export function Slide4({ step }: SlideProps) {
  return (
    <section className="slide s4" aria-labelledby="h-4">
      <Head index={4} />
      <div className="slide-body s4-body">
        <ol className="s4-rail" aria-label="Этапы обработки">
          <span className="s4-line" aria-hidden="true"><i /></span>
          {STAGES.map((s, i) => (
            <m.li key={s.t} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.09, duration: 0.5, ease: EASE }}>
              <span className="s4-dot mono" aria-hidden="true">{i + 1}</span>
              <h3 className="h3">{s.t}</h3>
              <p className="small">{s.d}</p>
            </m.li>
          ))}
        </ol>
        <m.ul
          className="s4-rules" aria-label="Принципы"
          initial={false} animate={{ opacity: step >= 1 ? 1 : 0, y: step >= 1 ? 0 : 16 }}
          transition={{ duration: 0.5, ease: EASE }} aria-hidden={step < 1}
        >
          {RULES.map((r) => (
            <li key={r.t}>
              <h3 className="h3">{r.t}</h3>
              <p className="small">{r.d}</p>
            </li>
          ))}
        </m.ul>
      </div>
      <div className="slide-foot">
        <span className="label">Python · FastAPI · PostgreSQL · фоновый воркер · React. Развёрнуто в облаке на синтетических данных.</span>
      </div>
    </section>
  );
}
