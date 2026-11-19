import { useEffect, useMemo, useState } from "react";
import { m } from "motion/react";
import { GRAPH_H, GRAPH_W, buildTopology, type TopoId } from "../data/topologies";
import { OBSERVATIONS, evaluate, partition, type DatasetId, type HypId } from "../data/hypotheses";
import { Network, type Tone } from "../ui/Network";
import { Reveal, SlideHeader, StatusIcon } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

const ITEMS = [
  { id: "funnel", name: "Воронка", group: "Структура" },
  { id: "fanout", name: "Веер", group: "Структура" },
  { id: "chain", name: "Цепочка", group: "Структура" },
  { id: "cycle", name: "Цикл", group: "Структура" },
  { id: "temporal", name: "Хронология потока", group: "Сигналы" },
  { id: "peer", name: "Статистика пиров", group: "Сигналы" },
  { id: "hyp", name: "Конкурирующие гипотезы", group: "Проверка" },
  { id: "evid", name: "Валидация доказательств", group: "Проверка" },
] as const;

const STRUCT_TEXT: Record<TopoId, { title: string; text: string }> = {
  funnel: { title: "Воронка сбора", text: "Несколько счетов направляют основную часть средств на один счёт, откуда деньги уходят дальше." },
  fanout: { title: "Веер распределения", text: "Один счёт получает средства и раздаёт их сразу многим получателям." },
  chain: { title: "Цепочка переводов", text: "Последовательные переводы через транзитные счета: каждый следующий перевод идёт после предыдущего." },
  cycle: { title: "Круговой поток", text: "Средства возвращаются к источнику. Цикл засчитывается, только если порядок переводов по времени возможен." },
};

type TScenario = "confirmed" | "ambiguous" | "contradicted";
const TEMPORAL: Record<TScenario, { label: string; chip: string; text: string; tone: Tone; outDay: number; icon: "supported" | "ambiguous" | "contradicted" }> = {
  confirmed: { label: "Подтверждена", chip: "ok", text: "Вывод средств идёт позже поступлений: деньги физически могли пройти через счёт.", tone: "legit", outDay: 5, icon: "supported" },
  ambiguous: { label: "Неоднозначна", chip: "warn", text: "Вывод в тот же день, что и последнее поступление. В источнике только даты, порядок внутри дня неизвестен.", tone: "warn", outDay: 3, icon: "ambiguous" },
  contradicted: { label: "Противоречит", chip: "risk", text: "Вывод раньше поступления: эти деньги не могли пройти через счёт. Связь не засчитывается.", tone: "risk", outDay: 1, icon: "contradicted" },
};

function Legend() {
  return (
    <div className="legend">
      <span><i style={{ background: "var(--cyan)" }} />Вход</span>
      <span><i style={{ background: "var(--violet)" }} />Центр</span>
      <span><i style={{ background: "var(--pink)" }} />Выход</span>
      <span className="a">→ направление перевода</span>
    </div>
  );
}

function Timeline({ scenario }: { scenario: TScenario }) {
  const out = TEMPORAL[scenario].outDay;
  const gutter = 160, cols = 7, cw = (700 - gutter - 10) / cols;
  const inflow = [1, 2, 3];
  const colX = (d: number) => gutter + (d - 1) * cw;
  return (
    <svg className="instr" viewBox="0 0 700 190" role="img" aria-label={`Шкала по дням: поступления в дни 1–3, вывод в день ${out}`}>
      {Array.from({ length: cols }, (_, i) => (
        <g key={i}>
          <line x1={colX(i + 1) + cw / 2} x2={colX(i + 1) + cw / 2} y1="14" y2="134" stroke="rgb(255 255 255 / 0.08)" />
          <text x={colX(i + 1) + cw / 2} y="174" textAnchor="middle" className="axis">д.{i + 1}</text>
        </g>
      ))}
      <text x="0" y="62" className="axis" fill="var(--cyan)">поступления</text>
      <text x="0" y="122" className="axis" fill="var(--pink)">вывод</text>
      {inflow.map((d) => (
        <rect key={d} x={colX(d) + 8} y="36" width={cw - 16} height="36" rx="8" fill="var(--cyan)" opacity="0.85" />
      ))}
      <m.rect initial={false} animate={{ x: colX(out) + 8, fill: scenario === "confirmed" ? "#56d49e" : scenario === "ambiguous" ? "#f4c152" : "#ff6b86" }} y="96" width={cw - 16} height="36" rx="8" transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} />
    </svg>
  );
}

function pseudoDots() {
  return Array.from({ length: 40 }, (_, i) => {
    const u = (i + 0.5) / 40;
    return { x: 0.05 + 0.6 * Math.pow(u, 1.6), y: ((i * 53) % 7) - 3 };
  });
}
const DOTS = pseudoDots();

function PeerStrip({ outlier }: { outlier: boolean }) {
  const X = (f: number) => 40 + f * 620;
  const median = DOTS[20].x, thr = 0.78, subj = outlier ? 0.92 : 0.6;
  return (
    <svg className="instr" viewBox="0 0 700 190" role="img" aria-label={outlier ? "Счёт выше порога выброса" : "Счёт выше медианы группы, но ниже порога выброса"}>
      {DOTS.map((d, i) => <circle key={i} cx={X(d.x)} cy={110 + d.y * 9} r="7" fill="#6d7290" opacity="0.8" />)}
      <line x1={X(median)} x2={X(median)} y1="60" y2="160" stroke="var(--text-2)" strokeDasharray="4 6" />
      <text x={X(median)} y="184" textAnchor="middle" className="axis">медиана группы</text>
      <line x1={X(thr)} x2={X(thr)} y1="60" y2="160" stroke="var(--warn)" strokeDasharray="4 6" />
      <text x={X(thr)} y="184" textAnchor="middle" className="axis" fill="var(--warn)">порог выброса</text>
      <m.g initial={false} animate={{ x: X(subj) }} transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
        <circle cx="0" cy="110" r="14" fill="var(--violet)" stroke="#fff" strokeWidth="3" />
        <text x="0" y="40" textAnchor="middle" className="axis" fill="var(--violet-strong)">этот счёт</text>
        <line x1="0" x2="0" y1="46" y2="92" stroke="var(--violet)" />
      </m.g>
    </svg>
  );
}

const VERDICT_TEXT = {
  suspicious_explanation_favoured: { chip: "risk", title: "Перевес: подозрительное объяснение", effect: "Приоритет не меняется. Это сравнение только с проверяемыми альтернативами." },
  benign_explanation_favoured: { chip: "ok", title: "Перевес: легитимное объяснение", effect: "Приоритет ограничен до «Низкий». Формация, доказательства и сигналы остаются сохранёнными." },
  inconclusive: { chip: "warn", title: "Неопределённо", effect: "Данных недостаточно для перевеса." },
} as const;

const EVIDENCE = [
  { id: "in", text: "5 счетов направили основную часть средств на один счёт", n: "5 переводов", kind: "supported" as const },
  { id: "out", text: "Дальнейшее перечисление хронологически совместимо", n: "2 перевода", kind: "supported" as const },
  { id: "none", text: "Нет данных о владельцах и назначении платежей", n: "Чего система не знает", kind: "unavailable" as const },
];

export function Slide3({ step, setStep }: SlideProps) {
  const item = ITEMS[step];
  const [temporal, setTemporal] = useState<TScenario>("confirmed");
  const [outlier, setOutlier] = useState(false);
  const [hyp, setHyp] = useState<HypId>("suspicious");
  const [ds, setDs] = useState<DatasetId>("A");
  const [ev, setEv] = useState<string | null>(null);
  useEffect(() => { if (item.id !== "evid") setEv(null); }, [item.id]);

  const evaluation = useMemo(() => evaluate(ds), [ds]);
  const part = useMemo(() => partition(ds, hyp), [ds, hyp]);

  const topo: TopoId = item.id === "fanout" || item.id === "chain" || item.id === "cycle" ? item.id : "funnel";
  const graph = useMemo(() => {
    const tTone = TEMPORAL[temporal].tone;
    return buildTopology(topo, {
      hubPulse: item.id === "funnel" || item.id === "fanout" || item.id === "hyp",
      flow: true,
      labels: item.id === "funnel" ? { h: "центр" } : item.id === "evid" || item.id === "temporal" || item.id === "peer" ? { h: "··7530" } : undefined,
      tone: (id) => {
        if (item.id === "hyp") return hyp === "suspicious" ? "risk" : "legit";
        if (item.id === "evid" && ev === "none") return "dim";
        return id === "h" ? "hub" : id.startsWith("f") ? "source" : "sink";
      },
      edgeTone: (id) => {
        if (item.id === "temporal") return id.startsWith("ho") ? tTone : "source";
        if (item.id === "peer") return outlier ? "risk" : "neutral";
        if (item.id === "hyp") return hyp === "suspicious" ? "risk" : "legit";
        if (item.id === "evid") {
          if (ev === "in") return id.match(/^f\dh$/) ? "hub" : "dim";
          if (ev === "out") return id.startsWith("ho") ? "hub" : "dim";
          if (ev === "none") return "dim";
        }
        if (item.id === "cycle") return "risk";
        if (item.id === "chain") return "warn";
        return "hub";
      },
    });
  }, [topo, item.id, temporal, outlier, hyp, ev]);

  const verdict = VERDICT_TEXT[evaluation.verdict];

  return (
    <section className="slide" aria-labelledby="h-3">
      <Reveal><SlideHeader index={3} /></Reveal>
      <div className="slide-inner s3">
        <Reveal delay={0.1}>
          <h2 id="h-3" className="h1 s3-title">Не просто обнаруживаем. <span className="grad">Проверяем гипотезы</span></h2>
        </Reveal>

        <div className="s3-cols">
          <nav className="rail" aria-label="Компоненты движка">
            {(["Структура", "Сигналы", "Проверка"] as const).map((g) => (
              <div key={g} className="rail-group">
                <span className="label">{g}</span>
                {ITEMS.map((it, i) => it.group === g && (
                  <button key={it.id} className={i === step ? "on" : i < step ? "seen" : ""} aria-current={i === step ? "step" : undefined} onClick={() => setStep(i)}>
                    <span className="mono">{i + 1}</span>{it.name}
                  </button>
                ))}
              </div>
            ))}
          </nav>

          <div className="glass gpanel">
            <Network className="gsvg" width={GRAPH_W} height={GRAPH_H} nodes={graph.nodes} edges={graph.edges} duration={0.8} label={`Граф: ${item.name}`} />
            <div className="ginstr">
              {item.id === "temporal" && <Timeline scenario={temporal} />}
              {item.id === "peer" && <PeerStrip outlier={outlier} />}
              {item.id === "hyp" && (
                <div className="verdict" aria-live="polite">
                  <span className={`chip ${verdict.chip}`}>{verdict.title}</span>
                  <p>{verdict.effect}</p>
                  <p className="label">Иллюстративные наблюдения; правила оценки — как в движке ({OBSERVATIONS.length} независимых группы наблюдений).</p>
                </div>
              )}
              {(item.id === "funnel" || item.id === "fanout" || item.id === "chain" || item.id === "cycle" || item.id === "evid") && <Legend />}
              {item.id === "evid" && <p className="small ginote">{ev ? "Подсвечены переводы, на которых основан факт." : "Выберите факт справа: граф покажет переводы-источники."}</p>}
              {(item.id === "funnel" || item.id === "fanout" || item.id === "chain" || item.id === "cycle") && <p className="small ginote">Структура указывает, где смотреть, но не доказывает, что произошло.</p>}
            </div>
          </div>

          <m.div key={item.id} className="glass ppanel" initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
            {(item.id === "funnel" || item.id === "fanout" || item.id === "chain" || item.id === "cycle") && (
              <>
                <span className="chip violet">Структурный сигнал</span>
                <h3 className="h2">{STRUCT_TEXT[item.id].title}</h3>
                <p className="body">{STRUCT_TEXT[item.id].text}</p>
                <span className="chip">Кандидат, не вывод</span>
              </>
            )}
            {item.id === "temporal" && (
              <>
                <span className="chip cyan">Сигнал: время</span>
                <h3 className="h2">Хронология потока</h3>
                <div className="seg wrap" role="group" aria-label="Сценарий хронологии">
                  {(Object.keys(TEMPORAL) as TScenario[]).map((k) => (
                    <button key={k} className="btn" aria-pressed={temporal === k} onClick={() => setTemporal(k)}>{TEMPORAL[k].label}</button>
                  ))}
                </div>
                <div className="state" aria-live="polite">
                  <StatusIcon kind={TEMPORAL[temporal].icon} size={36} />
                  <div><b>{TEMPORAL[temporal].label}</b><p className="body">{TEMPORAL[temporal].text}</p></div>
                </div>
              </>
            )}
            {item.id === "peer" && (
              <>
                <span className="chip cyan">Сигнал: статистика</span>
                <h3 className="h2">Сравнение с похожими счетами</h3>
                <div className="seg wrap" role="group" aria-label="Положение счёта">
                  <button className="btn" aria-pressed={!outlier} onClick={() => setOutlier(false)}>Выше медианы</button>
                  <button className="btn" aria-pressed={outlier} onClick={() => setOutlier(true)}>Выброс</button>
                </div>
                <div className="state" aria-live="polite">
                  <StatusIcon kind={outlier ? "supported" : "ambiguous"} size={36} />
                  <div><b>{outlier ? "Подтверждает гипотезу" : "Контр-свидетельство"}</b>
                    <p className="body">{outlier ? "Концентрация оборота выше порога выброса среди счетов похожей активности." : "Концентрация выше медианы группы, но ниже порога выброса: аномалией не считается."}</p></div>
                </div>
              </>
            )}
            {item.id === "hyp" && (
              <>
                <div className="chips"><span className="chip violet">Hypothesis Engine</span><span className="chip warn">В разработке</span></div>
                <div className="seg wrap" role="group" aria-label="Объяснение">
                  <button className="btn" aria-pressed={hyp === "suspicious"} onClick={() => setHyp("suspicious")}>Подозрительное</button>
                  <button className="btn" aria-pressed={hyp === "legit"} onClick={() => setHyp("legit")}>Легитимное</button>
                </div>
                <div className="seg wrap" role="group" aria-label="Наблюдения">
                  <button className="btn" aria-pressed={ds === "A"} onClick={() => setDs("A")}>Наблюдения A</button>
                  <button className="btn" aria-pressed={ds === "B"} onClick={() => setDs("B")}>Наблюдения B</button>
                </div>
                <div className="evcols" aria-live="polite">
                  <EvList title="Подтверждает" kind="supported" rows={part.supports.map((o) => ({ t: o.title, s: o.seen[ds] }))} />
                  <EvList title="Противоречит" kind="contradicted" rows={part.contradicts.map((o) => ({ t: o.title, s: o.seen[ds] }))} />
                </div>
                {part.neutral.length > 0 && <p className="neutral">Не различает: {part.neutral.map((o) => o.title.toLowerCase()).join(", ")}</p>}
              </>
            )}
            {item.id === "evid" && (
              <>
                <div className="chips"><span className="chip ok">В продукте</span></div>
                <ul className="evrows">
                  {EVIDENCE.map((e) => (
                    <li key={e.id}>
                      <button className={ev === e.id ? "on" : ""} aria-pressed={ev === e.id} onClick={() => setEv(ev === e.id ? null : e.id)}>
                        <StatusIcon kind={e.kind} />
                        <span><b>{e.text}</b><small>{e.n}</small></span>
                      </button>
                    </li>
                  ))}
                </ul>
                <ul className="statuses" aria-label="Статусы доказательств">
                  <li><StatusIcon kind="supported" size={26} />Подтверждает</li>
                  <li><StatusIcon kind="ambiguous" size={26} />Неоднозначно</li>
                  <li><StatusIcon kind="contradicted" size={26} />Противоречит</li>
                  <li><StatusIcon kind="unavailable" size={26} />Нет данных</li>
                </ul>
              </>
            )}
          </m.div>
        </div>
      </div>
    </section>
  );
}

function EvList({ title, kind, rows }: { title: string; kind: "supported" | "contradicted" | "unavailable"; rows: { t: string; s: string }[] }) {
  return (
    <div className="evlist">
      <div className="evh"><StatusIcon kind={kind} size={26} /><b>{title}</b><span className="mono">{rows.length}</span></div>
      {rows.length === 0 ? <p className="label">—</p> : rows.map((r) => (
        <p key={r.t} className="evi"><b>{r.t}</b><span>{r.s}</span></p>
      ))}
    </div>
  );
}
