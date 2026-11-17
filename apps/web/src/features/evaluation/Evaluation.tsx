import { useSearchParams } from "react-router-dom";
import { BandBadge, Empty, ErrorState, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime, formatRatio, shortId } from "../../lib/format";
import { kindLabel, t, tDynamic } from "../../lib/i18n";
import type { Band, BenchmarkExperiment, BenchmarkReport, BenchmarkRunList, ExampleNetwork, MethodSplitResult, ScenarioMetrics } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { comparatorMethod, defaultSplit, familyGroups, parseOutcomeReason, parseTransitions, primaryMethod, resultFor, resultsForSplit } from "./model";

const methodName = (m: string) => tDynamic("method.", m);
const methodShort = (m: string) => tDynamic("methodShort.", m, methodName(m));
const familyName = (f: string) => tDynamic("family.", f);
const num = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? t("eval.none") : v.toLocaleString("ru-RU", { maximumFractionDigits: digits });

/** Single-hue magnitude bar for a ratio; decorative — the number beside it carries the value. */
function Meter({ value }: { value: number | null | undefined }) {
  const pct = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <span className="meter" aria-hidden="true">
      <span className="meter__fill" style={{ width: `${pct}%` }} />
    </span>
  );
}

function Ratio({ value, ci }: { value: number | null | undefined; ci?: number[] | null }) {
  return (
    <span className="num" title={ci ? t("eval.ci", { lo: formatRatio(ci[0]), hi: formatRatio(ci[1]) }) : undefined}>
      {formatRatio(value)}
      {ci && <span className="subtle eval-ci"> {`${formatRatio(ci[0], 0)}–${formatRatio(ci[1], 0)}`}</span>}
    </span>
  );
}

export function Evaluation() {
  const [params, setParams] = useSearchParams();
  const runs = useApi("eval:runs", (s) => api.get<BenchmarkRunList>("/api/v1/evaluation/runs", undefined, s));
  const label = params.get("run") ?? runs.data?.latest ?? null;
  const report = useApi(label ? `eval:run:${label}` : null, (s) =>
    api.get<BenchmarkReport>(`/api/v1/evaluation/runs/${encodeURIComponent(label ?? "")}`, undefined, s),
  );
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    if (key === "run") next.delete("split");
    setParams(next, { replace: true });
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t("eval.title")}</h1>
          <p>{t("eval.subtitle")}</p>
        </div>
      </div>
      <div className="callout callout--warn" role="note" data-testid="eval-disclaimer">
        <strong>{t("eval.disclaimerTitle")}.</strong> {t("eval.disclaimerBody")}
      </div>
      {runs.error?.code === "BENCHMARK_NOT_RUN" ? (
        <Panel>
          <Empty title={t("eval.notRunTitle")}>
            <span>{t("eval.notRunBody")}</span>
          </Empty>
        </Panel>
      ) : runs.error ? (
        <ErrorState error={runs.error} onRetry={runs.reload} />
      ) : null}
      {runs.loading && !runs.data && <Loading />}
      {report.error && <ErrorState error={report.error} onRetry={report.reload} />}
      {label && !report.data && report.loading && <Loading rows={8} />}
      {runs.data && report.data && (
        <ReportView report={report.data} runs={runs.data} split={params.get("split") ?? defaultSplit(report.data)} errorMethod={params.get("errors")} onChange={set} />
      )}
    </div>
  );
}

function ReportView(props: {
  report: BenchmarkReport;
  runs: BenchmarkRunList;
  split: string;
  errorMethod: string | null;
  onChange: (key: string, value: string) => void;
}) {
  const { report, runs, onChange } = props;
  const split = report.run.splits_evaluated.includes(props.split) ? props.split : defaultSplit(report);
  const rows = resultsForSplit(report, split);
  const primary = primaryMethod(report);
  return (
    <>
      <div className="row eval-controls">
        <label className="field">
          <span>{t("eval.run")}</span>
          <select className="select" value={report.label} onChange={(e) => onChange("run", e.target.value)} data-testid="eval-run">
            {runs.runs.map((r) => (
              <option key={r.label} value={r.label}>
                {`${r.label} · ${formatDateTime(r.created_at)}`}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t("eval.split")}</span>
          <select className="select" value={split} onChange={(e) => onChange("split", e.target.value)} data-testid="eval-split">
            {report.run.splits_evaluated.map((s) => (
              <option key={s} value={s}>
                {tDynamic("eval.split.", s)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {split === "test" && <p className="subtle">{t("eval.testSealedNote")}</p>}
      <Headline report={report} split={split} />
      <Panel title={t("eval.methods")} hint={t("eval.methodsHint")} flush id="eval-methods">
        <ScenarioTable rows={rows} report={report} primary={primary} />
      </Panel>
      <Panel title={t("eval.queue")} hint={t("eval.queueHint")} flush>
        <QueueTable rows={rows} />
      </Panel>
      <Panel title={t("eval.families")} hint={t("eval.familiesHint")} flush id="eval-families">
        <FamilyTable report={report} rows={rows} primary={primary} />
      </Panel>
      <ErrorsPanel report={report} split={split} method={props.errorMethod} onChange={onChange} />
      {report.experiments.length > 0 && (
        <>
          <Panel title={t("eval.ablations")} hint={t("eval.ablationsHint")} flush>
            <ExperimentTable rows={report.experiments.filter((e) => e.kind === "ablation")} showMethod={false} />
          </Panel>
          <Panel title={t("eval.robustness")} hint={t("eval.robustnessHint")} flush>
            <ExperimentTable rows={report.experiments.filter((e) => e.kind === "robustness")} showMethod />
          </Panel>
        </>
      )}
      <div className="grid-2">
        <Panel title={t("eval.ttd")} hint={t("eval.ttdHint")}>
          <ul className="reason-list">
            {report.time_to_detection
              .filter((x) => x.split === split)
              .map((x) => (
                <li key={x.method}>
                  <strong>{methodName(x.method)}</strong>
                  <div className="subtle">
                    {t("eval.ttdRow", {
                      median: x.median_days === null ? t("eval.none") : t("eval.days", { n: x.median_days }),
                      max: x.max_days === null ? t("eval.none") : t("eval.days", { n: x.max_days }),
                      detected: x.detected_networks,
                      undetected: x.undetected_networks,
                      transient: x.transient_detections,
                    })}
                  </div>
                </li>
              ))}
          </ul>
        </Panel>
        <Panel title={t("eval.scale")} hint={t("eval.scaleHint")}>
          {report.scale.length === 0 ? (
            <p className="muted">{t("eval.none")}</p>
          ) : (
            <ul className="reason-list">
              {report.scale.map((s) => (
                <li key={s.method}>
                  <strong>{methodName(s.method === "B4_v1" ? "B4_v1_structural_temporal" : s.method)}</strong>
                  <div className="subtle">
                    {t("eval.scaleRow", { tx: s.transactions, accounts: s.accounts, formations: s.formations, seconds: num(s.wall_seconds) })}
                  </div>
                  {s.partial_reasons.length > 0 && <div className="subtle">{t("eval.partial", { reasons: s.partial_reasons.join(", ") })}</div>}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <Provenance report={report} />
    </>
  );
}

function Headline({ report, split }: { report: BenchmarkReport; split: string }) {
  const primary = primaryMethod(report);
  const comparator = comparatorMethod(report);
  const p = resultFor(report, split, primary);
  const c = resultFor(report, split, comparator);
  if (!p || !primary) return null;
  const p10 = (r?: MethodSplitResult) => r?.queue.find((q) => q.k === 10)?.precision;
  const tiles: { key: string; label: string; value: string; was?: string }[] = [
    { key: "f1", label: t("eval.kpi.f1"), value: formatRatio(p.scenario.f1), was: c && formatRatio(c.scenario.f1) },
    { key: "precision", label: t("eval.kpi.precision"), value: formatRatio(p.scenario.precision), was: c && formatRatio(c.scenario.precision) },
    { key: "recall", label: t("eval.kpi.recall"), value: formatRatio(p.scenario.recall), was: c && formatRatio(c.scenario.recall) },
    { key: "fpr", label: t("eval.kpi.fpr"), value: formatRatio(p.scenario.fpr), was: c && formatRatio(c.scenario.fpr) },
    { key: "p10", label: t("eval.kpi.p10"), value: formatRatio(p10(p)), was: c && formatRatio(p10(c)) },
    { key: "alerts", label: t("eval.kpi.alertsPerNet"), value: num(p.alerts.alerts_per_network), was: c && num(c.alerts.alerts_per_network) },
    { key: "bg", label: t("eval.kpi.bgAlerts"), value: num(p.alerts.background_alerts_per_network), was: c && num(c.alerts.background_alerts_per_network) },
  ];
  return (
    <section aria-labelledby="eval-headline" className="stack stack--sm">
      <h2 id="eval-headline">
        {t("eval.headline", { split: tDynamic("eval.split.", split) })} · {methodName(primary)}
      </h2>
      <div className="grid-kpi eval-kpis">
        {tiles.map((tile) => (
          <div key={tile.key} className="panel kpi" data-testid={`eval-kpi-${tile.key}`}>
            <div className="kpi__label">{tile.label}</div>
            <div className="kpi__value num">{tile.value}</div>
            {tile.was && comparator && <div className="kpi__hint">{t("eval.compareTo", { method: methodShort(comparator), value: tile.was })}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}

function MethodCell({ name, report, primary }: { name: string; report: BenchmarkReport; primary: string | null }) {
  const m = report.methods.find((x) => x.name === name);
  return (
    <th scope="row" className={name === primary ? "eval-primary" : undefined}>
      <span className="eval-method">{methodName(name)}</span>
      <span className="subtle eval-method__group">{m ? tDynamic("eval.group.", m.group) : ""}</span>
    </th>
  );
}

function ScenarioTable({ rows, report, primary }: { rows: MethodSplitResult[]; report: BenchmarkReport; primary: string | null }) {
  const ci = (s: ScenarioMetrics) => s.ci95;
  return (
    <div className="table-wrap">
      <table className="table" data-testid="eval-scenario-table">
        <caption className="visually-hidden">{t("eval.methods")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("eval.col.method")}</th>
            <th scope="col" className="right" title={t("eval.col.tpHint")}>
              {t("eval.col.tp")}
            </th>
            <th scope="col" className="right" title={t("eval.col.fpHint")}>
              {t("eval.col.fp")}
            </th>
            <th scope="col" className="right" title={t("eval.col.fnHint")}>
              {t("eval.col.fn")}
            </th>
            <th scope="col" className="right" title={t("eval.col.tnHint")}>
              {t("eval.col.tn")}
            </th>
            <th scope="col">{t("eval.col.precision")}</th>
            <th scope="col">{t("eval.col.recall")}</th>
            <th scope="col">{t("eval.col.f1")}</th>
            <th scope="col" className="right">
              {t("eval.col.fpr")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.fnr")}
            </th>
            <th scope="col" className="right">{t("eval.col.abstained")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.method}>
              <MethodCell name={r.method} report={report} primary={primary} />
              <td className="right num">{r.scenario.tp}</td>
              <td className="right num">{r.scenario.fp}</td>
              <td className="right num">{r.scenario.fn}</td>
              <td className="right num">{r.scenario.tn}</td>
              <td>
                <Ratio value={r.scenario.precision} ci={ci(r.scenario).precision} />
              </td>
              <td>
                <Ratio value={r.scenario.recall} ci={ci(r.scenario).recall} />
              </td>
              <td className="eval-bar-cell">
                <span className="num">{formatRatio(r.scenario.f1)}</span>
                <Meter value={r.scenario.f1} />
              </td>
              <td className="right num">{formatRatio(r.scenario.fpr)}</td>
              <td className="right num">{formatRatio(r.scenario.fnr)}</td>
              <td className="right num">{r.abstentions.on_suspicious}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QueueTable({ rows }: { rows: MethodSplitResult[] }) {
  const q = (r: MethodSplitResult, k: number) => r.queue.find((x) => x.k === k);
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">{t("eval.queue")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("eval.col.method")}</th>
            <th scope="col" className="right">
              {t("eval.col.pAt", { k: 10 })}
            </th>
            <th scope="col" className="right">
              {t("eval.col.pAt", { k: 25 })}
            </th>
            <th scope="col" className="right">
              {t("eval.col.rAt", { k: 25 })}
            </th>
            <th scope="col" className="right">
              {t("eval.col.rAt", { k: 50 })}
            </th>
            <th scope="col" className="right">{t("eval.col.alerts")}</th>
            <th scope="col" className="right">{t("eval.col.alertPrecision")}</th>
            <th scope="col" className="right">{t("eval.col.alertsPerNet")}</th>
            <th scope="col" className="right">{t("eval.col.bgPerNet")}</th>
            <th scope="col" className="right">{t("eval.col.accPrecision")}</th>
            <th scope="col" className="right">{t("eval.col.accRecall")}</th>
            <th scope="col" className="right">{t("eval.col.latency")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.method}>
              <th scope="row">{methodName(r.method)}</th>
              <td className="right num">{formatRatio(q(r, 10)?.precision)}</td>
              <td className="right num">{formatRatio(q(r, 25)?.precision)}</td>
              <td className="right num">{formatRatio(q(r, 25)?.recall)}</td>
              <td className="right num">{formatRatio(q(r, 50)?.recall)}</td>
              <td className="right num">{r.alerts.raised}</td>
              <td className="right num">{formatRatio(r.alerts.precision)}</td>
              <td className="right num">{num(r.alerts.alerts_per_network)}</td>
              <td className="right num">{num(r.alerts.background_alerts_per_network)}</td>
              <td className="right num">{formatRatio(r.accounts.precision)}</td>
              <td className="right num">{formatRatio(r.accounts.recall)}</td>
              <td className="right num">{`${num(r.latency_ms.median, 1)} / ${num(r.latency_ms.p95, 1)}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FamilyTable({ report, rows, primary }: { report: BenchmarkReport; rows: MethodSplitResult[]; primary: string | null }) {
  const rate = (r: MethodSplitResult, fam: string) => r.by_family.find((f) => f.family === fam);
  return (
    <div className="table-wrap">
      <table className="table" data-testid="eval-family-table">
        <caption className="visually-hidden">{t("eval.families")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("eval.families")}</th>
            {rows.map((r) => (
              <th key={r.method} scope="col" className={`right${r.method === primary ? " eval-primary" : ""}`} title={methodName(r.method)}>
                {methodShort(r.method)}
              </th>
            ))}
          </tr>
        </thead>
        {familyGroups(report).map((g) => (
          <tbody key={g.group}>
            <tr className="eval-group-row">
              <th scope="colgroup" colSpan={rows.length + 1}>
                {tDynamic("eval.group.", g.group)}
                <span className="subtle"> · {tDynamic("eval.rate.", g.group === "suspicious" ? "detection_rate" : "false_positive_rate")}</span>
              </th>
            </tr>
            {g.families.map((fam) => {
              const n = rows[0] ? rate(rows[0], fam)?.networks : undefined;
              return (
                <tr key={fam}>
                  <th scope="row">
                    {familyName(fam)}
                    {n !== undefined && <div className="subtle">{t("eval.networks", { count: n })}</div>}
                  </th>
                  {rows.map((r) => (
                    <td key={r.method} className={`right num${r.method === primary ? " eval-primary" : ""}`}>
                      {formatRatio(rate(r, fam)?.rate, 0)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function ExampleRow({ ex }: { ex: ExampleNetwork }) {
  const { outcome, kinds } = parseOutcomeReason(ex.reason);
  return (
    <li className="eval-example">
      <div className="row eval-example__head">
        <strong>{familyName(ex.family)}</strong>
        <span className="badge badge--outline">{ex.variant}</span>
        <span className="badge badge--outline">{tDynamic("difficulty.", ex.difficulty)}</span>
        <code className="mono subtle">{ex.network_id}</code>
      </div>
      <dl className="kv eval-example__kv">
        <dt>{t("eval.expected")}</dt>
        <dd>{tDynamic("expected.", ex.expected)}</dd>
        <dt>{t("eval.outcome")}</dt>
        <dd>
          {tDynamic("outcome.", outcome)}
          {kinds.length > 0 && ` · ${kinds.map((k) => kindLabel(k, true)).join(", ")}`}
        </dd>
      </dl>
      {ex.alerts.map((a, i) => (
        <div key={i} className="row eval-example__alert">
          {a.band && <BandBadge band={a.band as Band} />}
          <span>{kindLabel(a.kind)}</span>
          <span className="eval-codes">
            {a.reasons.map((c) => (
              <code key={c} className="mono subtle">
                {c}
              </code>
            ))}
          </span>
        </div>
      ))}
    </li>
  );
}

function FamilyCounts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return <p className="subtle">{t("eval.byFamily", { list: entries.map(([f, n]) => `${familyName(f)} — ${n}`).join("; ") })}</p>;
}

function ErrorsPanel({ report, split, method, onChange }: { report: BenchmarkReport; split: string; method: string | null; onChange: (k: string, v: string) => void }) {
  const available = report.examples.filter((e) => e.split === split);
  if (available.length === 0) return null;
  const chosen = available.find((e) => e.method === method) ?? available.find((e) => e.method === primaryMethod(report)) ?? available[0]!;
  return (
    <Panel
      title={t("eval.errors")}
      hint={t("eval.errorsHint")}
      id="eval-errors"
      actions={
        <select className="select" value={chosen.method} onChange={(e) => onChange("errors", e.target.value)} aria-label={t("eval.col.method")}>
          {available.map((e) => (
            <option key={e.method} value={e.method}>
              {methodName(e.method)}
            </option>
          ))}
        </select>
      }
    >
      <div className="grid-2">
        <section className="stack stack--sm" aria-labelledby="eval-fp">
          <h3 id="eval-fp">{t("eval.fp", { count: chosen.false_positive_count })}</h3>
          <FamilyCounts counts={chosen.false_positives_by_family} />
          {chosen.false_positives.length === 0 ? (
            <p className="muted">{t("eval.noErrors")}</p>
          ) : (
            <ul className="eval-examples">
              {chosen.false_positives.map((ex) => (
                <ExampleRow key={ex.network_id} ex={ex} />
              ))}
            </ul>
          )}
        </section>
        <section className="stack stack--sm" aria-labelledby="eval-fn">
          <h3 id="eval-fn">{t("eval.fn", { count: chosen.false_negative_count })}</h3>
          <FamilyCounts counts={chosen.false_negatives_by_family} />
          <p className="subtle">{t("eval.abstainNote")}</p>
          {chosen.false_negatives.length === 0 ? (
            <p className="muted">{t("eval.noErrors")}</p>
          ) : (
            <ul className="eval-examples">
              {chosen.false_negatives.map((ex) => (
                <ExampleRow key={ex.network_id} ex={ex} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </Panel>
  );
}

function ExperimentTable({ rows, showMethod }: { rows: BenchmarkExperiment[]; showMethod: boolean }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">{showMethod ? t("eval.robustness") : t("eval.ablations")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("eval.col.experiment")}</th>
            {showMethod && <th scope="col">{t("eval.col.method")}</th>}
            <th scope="col" className="right">
              {t("eval.col.precision")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.recall")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.f1")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.fpr")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.pAt", { k: 10 })}
            </th>
            <th scope="col" className="right">{t("eval.col.alertsPerNet")}</th>
            <th scope="col" className="right">{t("eval.col.changed")}</th>
            <th scope="col">{t("eval.col.transitions")}</th>
            <th scope="col">{t("eval.col.bands")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => {
            const base = e.name.replace(/ \[.*\]$/, "");
            const moves = parseTransitions(e.transitions);
            return (
              <tr key={e.name}>
                <th scope="row" title={e.description}>
                  {tDynamic("exp.", base)}
                </th>
                {showMethod && <td title={methodName(e.method)}>{methodShort(e.method)}</td>}
                <td className="right num">{formatRatio(e.scenario.precision)}</td>
                <td className="right num">{formatRatio(e.scenario.recall)}</td>
                <td className="right num">{formatRatio(e.scenario.f1)}</td>
                <td className="right num">{formatRatio(e.scenario.fpr)}</td>
                <td className="right num">{formatRatio(e.precision_at_10)}</td>
                <td className="right num">{num(e.alerts_per_network)}</td>
                <td className="right num">{e.changed}</td>
                <td className="eval-moves">
                  {moves.length === 0
                    ? t("eval.none")
                    : moves.map((m) => (
                        <div key={`${m.family}${m.from}${m.to}`}>
                          {`${familyName(m.family)}: ${m.from}→${m.to} ×${m.count}`}
                        </div>
                      ))}
                </td>
                <td className="eval-moves">
                  {Object.keys(e.band_changes).length === 0
                    ? t("eval.none")
                    : Object.entries(e.band_changes).map(([k, v]) => {
                        const [from = "", to = ""] = k.split("->");
                        return <div key={k}>{`${tDynamic("band.", from)} → ${tDynamic("band.", to)} ×${v}`}</div>;
                      })}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Provenance({ report }: { report: BenchmarkReport }) {
  const run = report.run;
  return (
    <div className="grid-2">
      <Panel title={t("eval.provenance")}>
        <dl className="kv">
          <dt>{t("eval.version")}</dt>
          <dd>
            <code className="mono">{report.suite.benchmark_version}</code>
          </dd>
          <dt>{t("eval.seed")}</dt>
          <dd className="num">{report.suite.master_seed}</dd>
          <dt>{t("eval.commit")}</dt>
          <dd>
            <code className="mono" title={run.code_commit ?? undefined}>
              {run.code_commit ? shortId(run.code_commit, 12) : t("eval.none")}
            </code>
            {run.code_dirty && <span className="subtle"> · {t("eval.dirty")}</span>}
          </dd>
          <dt>{t("eval.created")}</dt>
          <dd>{formatDateTime(run.created_at)}</dd>
          <dt>{t("eval.duration")}</dt>
          <dd className="num">{`${num(run.duration_s, 1)} s`}</dd>
          <dt>{t("eval.host")}</dt>
          <dd>{[run.cpu, run.cpu_count ? `× ${run.cpu_count}` : null, run.python && `Python ${run.python}`, run.networkx && `networkx ${run.networkx}`].filter(Boolean).join(" · ")}</dd>
          {report.suite.splits.map((s) => (
            <div key={s.split} className="kv__group">
              <dt>{t("eval.manifest", { split: s.split })}</dt>
              <dd>
                <code className="mono eval-hash">{s.data_manifest_sha256}</code>
                <div className="subtle">
                  {`${t("eval.networks", { count: s.networks })} · ${s.transactions} tx · ${s.suspicious}/${s.benign}`}
                </div>
              </dd>
            </div>
          ))}
          {report.methods.map((m) => (
            <div key={m.name} className="kv__group">
              <dt>{methodName(m.name)}</dt>
              <dd>
                {m.config_sha256 ? (
                  <code className="mono eval-hash" title={t("eval.config")}>
                    {m.config_sha256}
                  </code>
                ) : (
                  <span className="subtle">{`${t("eval.threshold")}: ${num(m.threshold, 4)}`}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </Panel>
      <Panel title={t("eval.units")}>
        <ul className="reason-list">
          <li>{t("eval.unit.scenario")}</li>
          <li>{t("eval.unit.alert")}</li>
          <li>{t("eval.unit.queue")}</li>
          <li>{t("eval.unit.account")}</li>
          <li>{t("eval.matching")}</li>
          <li>{t("eval.abstainNote")}</li>
        </ul>
      </Panel>
    </div>
  );
}
