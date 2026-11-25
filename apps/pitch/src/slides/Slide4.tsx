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

/** Stack as used in the repository (pyproject.toml, apps/web/package.json, Dockerfiles, CI). */
const STACK = [
  { t: "Анализ и API", d: ["Python", "FastAPI", "NetworkX"] },
  { t: "Данные", d: ["PostgreSQL", "SQLAlchemy", "Alembic"] },
  { t: "Интерфейс", d: ["React", "TypeScript", "Vite", "Cytoscape.js"] },
  { t: "Доставка и тесты", d: ["Docker", "Pytest", "Playwright"] },
];

/** What exists today — every item is verifiable in the repository or the live demo. */
const WORKS = [
  { t: "Живое демо", d: "Развёрнуто в облаке, вход по именным аккаунтам" },
  { t: "Мобильный интерфейс", d: "На русском, работает и на экране телефона" },
  { t: "Тесты и CI", d: "Pytest, Vitest и Playwright на каждом коммите" },
  { t: "Воспроизводимый бенчмарк", d: "30 наборов, 220 сетей, запуск одной командой" },
];

export function Slide4({ step }: SlideProps) {
  const works = step >= 1;
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
        <div className="s4-low">
          <m.ul
            className="s4-stack" aria-label="Технологии"
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: works ? 0 : 1, y: works ? -8 : 0 }}
            transition={{ duration: 0.45, delay: works ? 0 : 0.7, ease: EASE }} aria-hidden={works}
          >
            {STACK.map((g) => (
              <li key={g.t}>
                <h3 className="label caps">{g.t}</h3>
                <ul className="s4-chips">{g.d.map((x) => <li key={x} className="chip">{x}</li>)}</ul>
              </li>
            ))}
          </m.ul>
          <m.ul
            className="s4-works" aria-label="Что уже работает"
            initial={false} animate={{ opacity: works ? 1 : 0, y: works ? 0 : 16 }}
            transition={{ duration: 0.5, delay: works ? 0.15 : 0, ease: EASE }} aria-hidden={!works}
          >
            {WORKS.map((w) => (
              <li key={w.t}>
                <span className="s4-ok" aria-hidden="true" />
                <h3 className="h3">{w.t}</h3>
                <p className="small">{w.d}</p>
              </li>
            ))}
          </m.ul>
        </div>
      </div>
      <div className="slide-foot">
        <span className="label">{works ? "Всё перечисленное можно проверить в репозитории и в живом демо. Данные синтетические." : "Модульный монолит с очередью задач на PostgreSQL — минимум движущихся частей."}</span>
      </div>
    </section>
  );
}
