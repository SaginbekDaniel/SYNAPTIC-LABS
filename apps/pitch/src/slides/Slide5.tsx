import { m } from "motion/react";
import { EASE, Head } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

/** Real screenshots (1440 px wide, product build, synthetic demo-v1). Shown at ≤ 1:1, never upscaled. */
const SRC_W = 1440, VIEW_H = 900;
const FRAME_W = 1100;
const S = FRAME_W / SRC_W; // 0.76
const FRAME_H = VIEW_H * S;

interface View {
  key: string;
  tab: string;
  img: "queue" | "investigation";
  offset: number; // vertical scroll position in source px
  marks: { x: number; y: number; text: string }[]; // source px, relative to the visible window
}

const VIEWS: View[] = [
  {
    key: "queue", tab: "Очередь", img: "queue", offset: 0,
    marks: [
      { x: 300, y: 440, text: "Сети переводов, а не отдельные платежи" },
      { x: 905, y: 405, text: "Приоритет — очерёдность работы, не вероятность мошенничества" },
      { x: 1045, y: 480, text: "Предпросмотр: форма сети и основания до открытия дела" },
    ],
  },
  {
    key: "case", tab: "Расследование", img: "investigation", offset: 0,
    marks: [
      { x: 590, y: 545, text: "Граф только из транзакций-доказательств, толщина — сумма" },
      { x: 990, y: 296, text: "Почему это подозрительно — каждое основание раскрывается до транзакций" },
      { x: 1000, y: 688, text: "Отдельный блок: чего система не знает" },
    ],
  },
  {
    key: "decision", tab: "Решение", img: "investigation", offset: 1100,
    marks: [
      { x: 248, y: 282, text: "Исходные транзакции с идентификаторами" },
      { x: 1004, y: 90, text: "Действие и обоснование фиксирует аналитик" },
      { x: 1004, y: 650, text: "Журнал аудита только на добавление" },
    ],
  },
];

export function Slide5({ step, setStep }: SlideProps) {
  const v = VIEWS[step];
  return (
    <section className="slide s5" aria-labelledby="h-5">
      <Head index={5} />
      <div className="slide-body s5-body">
        <figure className="s5-frame" style={{ width: FRAME_W, height: FRAME_H }}>
          {(["queue", "investigation"] as const).map((img) => (
            <m.img
              key={img} src={`./shots/${img}.webp`} alt={img === "queue" ? "Экран «Проверки»: очередь сетей с предпросмотром" : "Экран расследования воронки ··7530"}
              width={SRC_W} draggable={false} decoding="async"
              style={{ width: FRAME_W }}
              initial={false}
              animate={{ opacity: v.img === img ? 1 : 0, y: img === "investigation" ? -(v.img === img ? v.offset : 0) * S : 0 }}
              transition={{ opacity: { duration: 0.45 }, y: { duration: 0.9, ease: EASE } }}
              aria-hidden={v.img !== img}
            />
          ))}
          {v.marks.map((mk, i) => (
            <m.span
              key={`${v.key}-${i}`} className="s5-mark mono" aria-hidden="true"
              style={{ left: mk.x * S, top: mk.y * S }}
              initial={{ opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.55 + i * 0.12, duration: 0.35, ease: EASE }}
            >{i + 1}</m.span>
          ))}
        </figure>

        <div className="s5-side">
          <div className="s5-tabs" role="group" aria-label="Экраны продукта">
            {VIEWS.map((x, i) => (
              <button key={x.key} className={`s5-tab ${i === step ? "on" : ""}`} aria-pressed={i === step} onClick={() => setStep(i)}>
                {x.tab}
              </button>
            ))}
          </div>
          <ol className="s5-notes" key={v.key}>
            {v.marks.map((mk, i) => (
              <m.li key={i} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 + i * 0.12, duration: 0.4, ease: EASE }}>
                <span className="s5-mark mono static" aria-hidden="true">{i + 1}</span>
                <span className="body t-1">{mk.text}</span>
              </m.li>
            ))}
          </ol>
          <p className="label s5-src">Реальные экраны развёрнутого прототипа. Демо-набор demo-v1, данные синтетические.</p>
        </div>
      </div>
    </section>
  );
}
