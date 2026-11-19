import { m } from "motion/react";
import { FUNNEL_EDGES, FUNNEL_FACTS, FUNNEL_NODES, MERCHANT_EDGES, MERCHANT_NODES, type GEdge, type GNode } from "../data/funnel";
import { Graph } from "../ui/Graph";
import { EASE, Head, Reveal } from "../ui/primitives";
import type { SlideProps } from "../ui/types";

interface Case {
  key: string;
  account: string;
  senders: number;
  nodes: GNode[];
  edges: GEdge[];
  truth: string;
  story: string;
  tone: "risk" | "ok";
}

const CASES: Case[] = [
  { key: "mule", account: "··7530", senders: 5, nodes: FUNNEL_NODES, edges: FUNNEL_EDGES, truth: "Воронка сбора", story: `Через ${FUNNEL_FACTS.lag} ${FUNNEL_FACTS.temporalShare} поступлений ушли дальше`, tone: "risk" },
  { key: "merchant", account: "··4418", senders: 5, nodes: MERCHANT_NODES, edges: MERCHANT_EDGES, truth: "Расчёты с мерчантом", story: "Обычная выплата выручки по графику", tone: "ok" },
];

/** Problem: an account-level rule produces two identical alerts; only the network reveals they are different. */
export function Slide2({ step }: SlideProps) {
  const net = step >= 1;
  return (
    <section className="slide s2" aria-labelledby="h-2">
      <Head index={2} />
      <div className="slide-body s2-body">
        {CASES.map((c, i) => (
          <Reveal key={c.key} delay={0.15 + i * 0.1} className="s2-col">
            <div className="s2-alert">
              <span className="s2-flag" aria-hidden="true" />
              <div>
                <div className="h3">Алерт по счёту <span className="mono">{c.account}</span></div>
                <div className="small">Правило «веерный приток»: {c.senders} отправителей за 3 дня</div>
              </div>
            </div>
            <div className="s2-graph">
              <Graph
                nodes={c.nodes} edges={c.edges} mono={!net}
                showNode={(n) => net || n.kind === "hub"} showEdge={() => net}
                title={net ? `${c.truth}: пять счетов → ${c.account} → два счёта` : `Счёт ${c.account} без окружения`}
                height={520}
              />
            </div>
            <m.div className="s2-truth" initial={false} animate={{ opacity: net ? 1 : 0, y: net ? 0 : 10 }} transition={{ duration: 0.5, delay: net ? 0.9 : 0, ease: EASE }} aria-hidden={!net}>
              <span className={`tag ${c.tone}`}>{c.truth}</span>
              <span className="small">{c.story}</span>
            </m.div>
          </Reveal>
        ))}
      </div>
      <div className="slide-foot">
        <span className="label">Слева — сценарий демо-набора demo-v1, справа — иллюстрация легитимной сети той же формы. Данные синтетические.</span>
      </div>
    </section>
  );
}
