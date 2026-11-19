import { useEffect, useState } from "react";
import { AnimatePresence, m } from "motion/react";
import { viewFor, type Rect } from "../engine/zoom";
import { DEMO_URL, REPO_URL } from "../data/links";
import { Reveal, SlideHeader } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const VW = 1060, VH = 560;

interface Spot { label: string; text: string; rect: Rect }
interface Screen { key: string; name: string; src: string; w: number; h: number; blurb: string; spots: Spot[] }

const SCREENS: Screen[] = [
  {
    key: "lab", name: "Fraud Lab", src: "shots/fraud-lab.webp", w: 1600, h: 1000,
    blurb: "Синтетические сценарии: подозрительные формации и легитимные двойники.",
    spots: [
      { label: "Набор сценариев", text: "Подозрительные формации и легитимные двойники. Метки сценариев детекторам не передаются.", rect: { x: 0.2, y: 0.39, w: 0.41, h: 0.38 } },
      { label: "Генерация и анализ", text: "Сгенерировать набор и запустить анализ — в одном экране.", rect: { x: 0.2, y: 0.9, w: 0.29, h: 0.07 } },
      { label: "Результат", text: "Найденные алерты появляются сразу после анализа.", rect: { x: 0.65, y: 0.68, w: 0.33, h: 0.32 } },
    ],
  },
  {
    key: "queue", name: "Review Queue", src: "shots/review-queue.webp", w: 1600, h: 1000,
    blurb: "Очередь проверок: приоритет — очерёдность работы, а не вероятность мошенничества.",
    spots: [
      { label: "Приоритет", text: "Приоритет — очерёдность проверки, а не вероятность мошенничества.", rect: { x: 0.185, y: 0.1, w: 0.5, h: 0.1 } },
      { label: "Поиск и фильтры", text: "Поиск по счёту, фильтры и сортировка работают на сервере по всему набору.", rect: { x: 0.2, y: 0.24, w: 0.49, h: 0.19 } },
      { label: "Быстрый просмотр", text: "Мини-граф и причины без перехода в расследование.", rect: { x: 0.72, y: 0.24, w: 0.26, h: 0.76 } },
    ],
  },
  {
    key: "graph", name: "Investigation Graph", src: "shots/graph.webp", w: 737, h: 694,
    blurb: "Только транзакции-доказательства. Толщина связи — сумма, стрелка — направление.",
    spots: [
      { label: "Входящие переводы", text: "Пять различных счетов направляют средства на один.", rect: { x: 0.04, y: 0.27, w: 0.4, h: 0.5 } },
      { label: "Центральный счёт", text: "Центр формации: куда сходятся переводы.", rect: { x: 0.4, y: 0.38, w: 0.2, h: 0.24 } },
      { label: "Исходящие переводы", text: "Дальнейшие переводы на два счёта.", rect: { x: 0.62, y: 0.4, w: 0.36, h: 0.2 } },
    ],
  },
  {
    key: "evidence", name: "Evidence", src: "shots/evidence.webp", w: 382, h: 690,
    blurb: "Каждый вывод — с источниками и оговорками.",
    spots: [
      { label: "Подтверждает гипотезу", text: "Факты со ссылкой на переводы-источники.", rect: { x: 0, y: 0.2, w: 1, h: 0.36 } },
      { label: "Чего система не знает", text: "Ограничения данных названы явно: нет владельцев, назначений платежей, времени суток.", rect: { x: 0, y: 0.6, w: 1, h: 0.4 } },
    ],
  },
  {
    key: "decision", name: "Analyst Decision", src: "shots/decision.webp", w: 382, h: 1089,
    blurb: "Решение принимает аналитик. Система только записывает его.",
    spots: [
      { label: "Действие и обоснование", text: "Статус кейса, действие и обоснование.", rect: { x: 0, y: 0.08, w: 1, h: 0.36 } },
      { label: "Без автоматических действий", text: "Система не блокирует счета и никому ничего не отправляет.", rect: { x: 0, y: 0.43, w: 1, h: 0.09 } },
      { label: "Журнал аудита", text: "Записи только добавляются: изменить или удалить нельзя.", rect: { x: 0, y: 0.68, w: 1, h: 0.31 } },
    ],
  },
];


export function Slide4({ step, setStep }: SlideProps) {
  const sc = SCREENS[step];
  const [sel, setSel] = useState<number | null>(0);
  useEffect(() => setSel(0), [step]);
  const v = viewFor(VW, VH, sc.w, sc.h, sel === null ? undefined : sc.spots[sel].rect);
  const base = import.meta.env.BASE_URL;

  return (
    <section className="slide" aria-labelledby="h-4">
      <Reveal><SlideHeader index={4} /></Reveal>
      <div className="slide-inner s4">
        <Reveal delay={0.1}><h2 id="h-4" className="h1 s4-title">От сигнала <span className="grad">до расследования</span></h2></Reveal>

        <ol className="journey" aria-label="Путь аналитика">
          {SCREENS.map((s, i) => (
            <li key={s.key} className={i === step ? "on" : i < step ? "done" : ""}>
              <button onClick={() => setStep(i)} aria-current={i === step ? "step" : undefined}>
                <span className="mono">{i + 1}</span>{s.name}
              </button>
            </li>
          ))}
        </ol>

        <div className="s4-main">
          <div className="glass vport" style={{ width: VW, height: VH }}>
            <AnimatePresence mode="popLayout" initial={false}>
              <m.div key={sc.key} className="vfill" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.45 }}>
                <m.div
                  className="vimg" style={{ width: sc.w, height: sc.h, transformOrigin: "0 0" }}
                  initial={false} animate={{ x: v.x, y: v.y, scale: v.s }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                >
                  <img src={`${base}${sc.src}`} width={sc.w} height={sc.h} alt={`Экран продукта: ${sc.name}`} draggable={false} />
                  {sc.spots.map((sp, i) => (
                    <button key={sp.label} tabIndex={-1} aria-hidden="true" className={`spot ${sel === i ? "on" : ""} ${sel !== null && sel !== i ? "faded" : ""}`}
                      style={{ left: `${sp.rect.x * 100}%`, top: `${sp.rect.y * 100}%`, width: `${sp.rect.w * 100}%`, height: `${sp.rect.h * 100}%` }}
                      onClick={() => setSel(sel === i ? null : i)}>
                      <span className="mono">{i + 1}</span>
                    </button>
                  ))}
                </m.div>
              </m.div>
            </AnimatePresence>
          </div>

          <div className="s4-side">
            <m.div key={sc.key} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="s4-copy">
              <span className="chip ok">Реальный экран · синтетические данные</span>
              <h3 className="h2">{sc.name}</h3>
              <p className="body">{sel === null ? sc.blurb : sc.spots[sel].text}</p>
            </m.div>
            <div className="spots" role="group" aria-label="Детали экрана">
              {sc.spots.map((sp, i) => (
                <button key={sp.label} className={`btn ${sel === i ? "active" : ""}`} aria-pressed={sel === i} onClick={() => setSel(sel === i ? null : i)}>
                  <span className="mono">{i + 1}</span>{sp.label}
                </button>
              ))}
              {sel !== null && <button className="btn" onClick={() => setSel(null)}>Весь экран</button>}
            </div>
            <div className="s4-link">
              <span className="small">Продукт развёрнут в облаке. Доступ к демо выдаём жюри, код открыт.</span>
              <div className="s4-links">
                <a className="btn" href={DEMO_URL} target="_blank" rel="noopener noreferrer">Живое демо ↗</a>
                <a className="btn" href={REPO_URL} target="_blank" rel="noopener noreferrer">GitHub ↗</a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
