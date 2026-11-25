import { FUNNEL_EDGES, FUNNEL_NODES } from "../data/funnel";
import { SLIDES } from "../data/notes";
import { Graph } from "../ui/Graph";
import { Reveal } from "../ui/primitives";

/** Cover: name, one-sentence purpose, scope disclaimer. The network motif is the case the whole deck follows. */
export function Slide1() {
  return (
    <section className="slide s1" aria-labelledby="h-1">
      <div className="s1-grid">
        <div className="s1-text">
          <Reveal y={12}><div className="eyebrow"><b>01</b><span>{SLIDES[0].eyebrow} · ITU Hackathon 2026</span></div></Reveal>
          <Reveal delay={0.08}><p className="s1-mark" aria-hidden="true">NEXORA</p></Reveal>
          <Reveal delay={0.16}><h2 className="s1-thesis" id="h-1">{SLIDES[0].headline}</h2></Reveal>
          <Reveal delay={0.24}><p className="lead s1-for">Для аналитиков антифрода и AML: очередь сетей переводов вместо россыпи алертов по счетам.</p></Reveal>
        </div>
        <Reveal delay={0.2} className="s1-art">
          <Graph nodes={FUNNEL_NODES} edges={FUNNEL_EDGES} title="Сеть переводов: пять счетов направляют деньги на один, он — дальше на два" byDay />
        </Reveal>
      </div>
      <Reveal delay={0.4} className="slide-foot">
        <span className="label">Прототип · синтетические данные · без интеграции с банком</span>
      </Reveal>
    </section>
  );
}
