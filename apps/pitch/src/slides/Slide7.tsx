import { m } from "motion/react";
import { WORKLOAD_RATIO, dec } from "../data/bench";
import { EASE, Head } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

/** Business value, one card per bank stakeholder. The only number is the measured queue ratio from slide 6. */
const CARDS = [
  { who: "Аналитику антифрода", big: `${dec(WORKLOAD_RATIO)}×`, bigLabel: "короче очередь, чем у правил", d: "Сети переводов вместо россыпи алертов. Форма и основания — в предпросмотре." },
  { who: "Комплаенсу и аудиту", big: "100 %", bigLabel: "показанных доказательств — с источником", d: "Каждое основание пересчитывается из исходных транзакций. Журнал аудита нельзя изменить." },
  { who: "Безопасности и рискам", big: "Человек", bigLabel: "принимает решение", d: "Система ничего не блокирует и не отправляет клиентам. Без генеративного ИИ — результат воспроизводим." },
];

/** What makes a pilot cheap to start; each item is a property of the current build. */
const EASY = [
  { t: "Вход", d: "Обычная выгрузка переводов в CSV" },
  { t: "Запуск", d: "Одна команда: Docker Compose" },
  { t: "Сравнение", d: "В теневом режиме — рядом с текущими правилами" },
];

export function Slide7({ step }: SlideProps) {
  const easy = step >= 1;
  return (
    <section className="slide s7" aria-labelledby="h-7">
      <Head index={7} />
      <div className="slide-body s7-body">
        <ul className="s7-cards" aria-label="Ценность для банка">
          {CARDS.map((c, i) => (
            <m.li key={c.who} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + i * 0.1, duration: 0.55, ease: EASE }}>
              <h3 className="label caps">{c.who}</h3>
              <p className="s7-big num">{c.big}</p>
              <p className="s7-biglabel small t-1">{c.bigLabel}</p>
              <p className="small">{c.d}</p>
            </m.li>
          ))}
        </ul>
        <m.div
          className="s7-easy" aria-label="Почему пилот быстро стартует" aria-hidden={!easy}
          initial={false} animate={{ opacity: easy ? 1 : 0, y: easy ? 0 : 16 }} transition={{ duration: 0.5, ease: EASE }}
        >
          <h3 className="label caps">Почему пилот просто начать</h3>
          <ul>
            {EASY.map((e) => (
              <li key={e.t}>
                <span className="s7-etag mono">{e.t}</span>
                <span className="small t-1">{e.d}</span>
              </li>
            ))}
          </ul>
        </m.div>
      </div>
      <div className="slide-foot">
        <span className="label">Прототип на синтетических данных, без интеграции с банком. Показатель очереди — из бенчмарка на слайде 6.</span>
      </div>
    </section>
  );
}
