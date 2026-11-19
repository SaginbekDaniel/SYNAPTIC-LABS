import { m } from "motion/react";
import { buildTopology, type TopoId } from "../data/topologies";
import { GRAPH_H, GRAPH_W } from "../data/topologies";
import { Network } from "../ui/Network";
import { Reveal, SlideHeader, StatusIcon } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

interface Stage { key: string; name: string; short: string; where: string; points: string[]; status?: string }

const STAGES: Stage[] = [
  { key: "tx", name: "Транзакции", short: "Импорт", where: "Лаборатория", points: ["CSV и синтетические сценарии", "Некорректные строки уходят в карантин, повторный импорт идемпотентен", "Только даты без времени суток: порядок внутри дня неизвестен"] },
  { key: "graph", name: "Финансовый граф", short: "Граф", where: "Граф связей", points: ["Счета — узлы, переводы — направленные рёбра", "Деньги — целые минимальные единицы, без дробных чисел", "Идентификаторы счетов — непрозрачные строки"] },
  { key: "pattern", name: "Поиск паттернов", short: "Паттерны", where: "Проверки", points: ["Структура: воронка, веер, цепочка, цикл", "Хронология: проверка по времени, один день — неоднозначно", "Статистика пиров: сравнение с похожими счетами"] },
  { key: "hyp", name: "Проверка гипотез", short: "Гипотезы", where: "Альтернативные объяснения", status: "В PR №3 · не в main", points: ["Подозрительное объяснение против легитимных альтернатив", "Зависимые наблюдения считаются один раз", "Непроверяемые альтернативы показываются явно"] },
  { key: "ev", name: "Доказательства", short: "Факты", where: "Расследование", points: ["Каждый факт ссылается на переводы-источники", "Статус: подтверждает · неоднозначно · противоречит · нет данных", "Раздел «Чего система не знает»"] },
  { key: "dec", name: "Решение аналитика", short: "Решение", where: "Расследование", points: ["Действие и обоснование записываются в журнал", "Журнал только на добавление", "Система не блокирует счета и ничего не отправляет"] },
];

function Visual({ k }: { k: string }) {
  if (k === "tx") {
    const rows = [["12.07.2026", "··1614", "··7530"], ["12.07.2026", "··7584", "··7530"], ["13.07.2026", "··1355", "··7530"], ["14.07.2026", "··6780", "··7530"], ["17.07.2026", "··7530", "··9459"]];
    return (
      <div className="v-ledger" role="table" aria-label="Пример реестра транзакций">
        <div className="row head" role="row"><span>Дата (только дата)</span><span>Отправитель</span><span /><span>Получатель</span></div>
        {rows.map((r, i) => (
          <m.div key={i} className="row" role="row" initial={{ opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 * i, duration: 0.5 }}>
            <span className="mono">{r[0]}</span><span className="mono">{r[1]}</span><span className="arr">→</span><span className="mono">{r[2]}</span>
          </m.div>
        ))}
      </div>
    );
  }
  if (k === "graph" || k === "ev") {
    const { nodes, edges } = buildTopology("funnel", { flow: true, tone: (id) => (k === "ev" && id === "h" ? "hub" : id === "h" ? "hub" : id.startsWith("f") ? "source" : "sink"), labels: { h: "··7530" } });
    return <Network className="fit" width={GRAPH_W} height={GRAPH_H} nodes={nodes} edges={edges} label="Граф переводов: воронка" />;
  }
  if (k === "pattern") {
    const names: [TopoId, string][] = [["funnel", "Воронка"], ["fanout", "Веер"], ["chain", "Цепочка"], ["cycle", "Цикл"]];
    return (
      <div className="v-patterns">
        {names.map(([t, n], i) => {
          const { nodes, edges } = buildTopology(t, { flow: true });
          return (
            <m.div key={t} className="mini" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1, duration: 0.5 }}>
              <Network className="fit" width={GRAPH_W} height={GRAPH_H} nodes={nodes} edges={edges} duration={0.01} label={n} />
              <span className="chip">{n}</span>
            </m.div>
          );
        })}
      </div>
    );
  }
  return null;
}

function Detail({ k }: { k: string }) {
  if (k === "hyp")
    return (
      <div className="v-hyp">
        <div className="hcard risk"><span className="chip risk">Подозрительное</span><b>Сбор средств через посредника</b></div>
        <div className="vs" aria-hidden="true">против</div>
        <div className="hcard ok"><span className="chip ok">Легитимные</span><b>Регулярная деловая активность · плановая выплата · займ</b></div>
        <p className="small hint">Не проверяются по транзакциям, показываются всегда: разовый легитимный сбор, личные переводы. Нужны данные KYC.</p>
      </div>
    );
  if (k === "ev")
    return (
      <ul className="v-ev">
        <li><StatusIcon kind="supported" /><span>5 различных счетов направили основную часть средств одному получателю</span></li>
        <li><StatusIcon kind="supported" /><span>Хронологически совместимо дальнейшее перечисление</span></li>
        <li><StatusIcon kind="unavailable" /><span>Нет данных о владельцах и назначении платежей</span></li>
      </ul>
    );
  if (k === "dec")
    return (
      <div className="v-dec">
        <ul className="acts" aria-label="Действия аналитика">
          <li>Взять в работу</li><li>Эскалировать</li><li>Отклонить гипотезу</li>
        </ul>
        <ol className="audit" aria-label="Журнал аудита">
          <li><i />Кейс открыт</li><li><i />Взят в работу</li><li><i />Закрыт · обоснование записано</li>
        </ol>
        <p className="small hint">Решение только записывается в журнал. Система не блокирует счета и никому ничего не отправляет.</p>
      </div>
    );
  return <Visual k={k} />;
}

export function Slide2({ step, setStep }: SlideProps) {
  const st = STAGES[step];
  return (
    <section className="slide" aria-labelledby="h-2">
      <Reveal><SlideHeader index={2} eyebrow="The solution" /></Reveal>
      <div className="slide-inner s2">
        <Reveal delay={0.1}><h2 id="h-2" className="h1 s2-title">NEXORA видит <span className="grad">всю финансовую картину</span></h2></Reveal>

        <ol className="pipe" aria-label="Конвейер NEXORA">
          {STAGES.map((s, i) => (
            <li key={s.key} className={i === step ? "on" : i < step ? "done" : ""}>
              <button onClick={() => setStep(i)} aria-current={i === step ? "step" : undefined} aria-label={`Шаг ${i + 1}: ${s.name}`}>
                <span className="n mono">{i + 1}</span>
                <span className="nm">{s.short}</span>
              </button>
              {i < STAGES.length - 1 && <span className="link" aria-hidden="true"><i style={{ transform: `scaleX(${i < step ? 1 : 0})` }} /></span>}
            </li>
          ))}
        </ol>

        <m.div key={st.key} className="glass s2-detail" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
          <div className="s2-text">
            <div className="s2-meta">
              <span className="chip violet">Шаг {step + 1} из 6</span>
              {st.status ? <span className="chip warn">{st.status}</span> : <span className="chip ok">В продукте</span>}
            </div>
            <h3 className="h2">{st.name}</h3>
            <ul>
              {st.points.map((p) => <li key={p}>{p}</li>)}
            </ul>
            <span className="label">Экран продукта: {st.where}</span>
          </div>
          <div className="s2-visual"><Detail k={st.key} /></div>
        </m.div>
      </div>
    </section>
  );
}
