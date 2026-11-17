import { useState } from "react";
import { Empty, ErrorState, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime, shortId } from "../../lib/format";
import { t, tDynamic, type MessageKey } from "../../lib/i18n";
import type { EvaluationReport, MethodSummary } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { defaultSplit, familyRows, groupExamples, num, pct, SPLIT_ORDER, type FamilyRow } from "./evaluationView";

const PRIMARY = "nexora_v2";
const REFERENCE = "nexora_v1";
const FAMILY_METHODS = [PRIMARY, REFERENCE, "B1_rules"] as const;

export function Evaluation() {
  const report = useApi("evaluation", (s) => api.get<EvaluationReport>("/api/v1/evaluation", undefined, s));
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t("eval.title")}</h1>
          <p>{t("eval.subtitle")}</p>
        </div>
      </div>
      <div className="callout callout--warn" role="note">
        {t("eval.synthetic")}
      </div>
      {report.loading && !report.data && <Loading rows={8} />}
      {report.error?.code === "BENCHMARK_NOT_FOUND" ? (
        <Panel>
          <Empty title={t("eval.emptyTitle")}>
            <span>{t("eval.emptyBody")}</span>
            <code className="mono">uv run python scripts/run_benchmark.py</code>
          </Empty>
        </Panel>
      ) : (
        report.error && <ErrorState error={report.error} onRetry={report.reload} />
      )}
      {report.data && <EvaluationBody report={report.data} />}
    </div>
  );
}

function EvaluationBody({ report }: { report: EvaluationReport }) {
  const [split, setSplit] = useState<string | null>(() => defaultSplit(report));
  const available = SPLIT_ORDER.filter((s) => s in report.results);
  const results = split ? report.results[split] : undefined;
  const info = split ? report.splits[split] : undefined;
  if (!split || !results) return null;
  return (
    <>
      <div className="row" role="group" aria-label={t("eval.split")}>
        <div className="segmented">
          {available.map((s) => (
            <button key={s} type="button" className="segmented__item" aria-pressed={s === split} onClick={() => setSplit(s)}>
              {tDynamic("eval.split.", s)}
            </button>
          ))}
        </div>
        {info && (
          <span className="subtle" data-testid="split-meta">
            {t("eval.splitMeta", { datasets: info.datasets, from: info.seeds[0] ?? 0, to: info.seeds[1] ?? 0 })} ·{" "}
            {tDynamic("eval.splitRole.", split)}
          </span>
        )}
      </div>

      <Headline current={results[PRIMARY]} reference={results[REFERENCE]} />

      <Panel title={t("eval.methods")} hint={t("eval.methodsHint")} flush id="eval-methods">
        <MethodTable report={report} results={results} />
      </Panel>

      <Panel title={t("eval.families")} hint={t("eval.familiesHint")} flush id="eval-families">
        <FamilyTable results={results} />
      </Panel>

      {report.ablations[split] && (
        <Panel title={t("eval.ablations")} hint={t("eval.ablationsHint")} flush>
          <VariantTable rows={Object.entries(report.ablations[split]).map(([id, s]) => ({ label: tDynamic("eval.ablation.", id), summary: s }))} />
        </Panel>
      )}

      {report.robustness && (
        <Panel title={t("eval.robustness")} hint={t("eval.robustnessHint")} flush>
          <VariantTable
            showIdentical
            rows={[
              { label: t("eval.pert.none"), summary: report.robustness.base },
              ...report.robustness.perturbations.map((p) => ({ label: tDynamic("eval.pert.", p.id, p.description), summary: p.summary, identical: p.identical_to_base })),
            ]}
          />
        </Panel>
      )}

      {report.sensitivity && (
        <Panel title={t("eval.sensitivity")} flush>
          <VariantTable rows={report.sensitivity.variants.map((v) => ({ label: v.id, summary: v.summary, mono: true }))} />
        </Panel>
      )}

      {report.examples && <Examples report={report} />}

      <div className="grid-2">
        <Panel title={t("eval.protocol")}>
          <ul className="plain-list">
            {(["eval.protocol.matching", "eval.protocol.flagged", "eval.protocol.units", "eval.protocol.baselines"] as MessageKey[]).map((k) => (
              <li key={k}>{t(k)}</li>
            ))}
          </ul>
        </Panel>
        <Panel title={t("eval.run")}>
          <dl className="kv" data-testid="eval-run">
            <dt>{t("eval.run.generated")}</dt>
            <dd>{formatDateTime(report.generated_at)}</dd>
            <dt>{t("eval.run.commit")}</dt>
            <dd>
              <code className="mono" title={report.code.commit}>
                {shortId(report.code.commit, 12)}
              </code>{" "}
              <span className="subtle">· {report.code.dirty ? t("eval.run.dirty") : t("eval.run.clean")}</span>
            </dd>
            <dt>{t("eval.run.generator")}</dt>
            <dd>
              <code className="mono">{report.generator.version}</code>
            </dd>
            <dt>{t("eval.run.config")}</dt>
            <dd>
              <code className="mono">
                {report.config.detectors_version} · {report.config.policy_version}
              </code>
            </dd>
            <dt>{t("eval.run.runtime")}</dt>
            <dd>{t("eval.run.seconds", { n: num(report.runtime_seconds) })}</dd>
          </dl>
        </Panel>
      </div>

      <Panel title={t("eval.lim.title")}>
        <ul className="plain-list">
          {(["eval.lim.synthetic", "eval.lim.small", "eval.lim.priority", "eval.lim.latency", "eval.lim.capped"] as MessageKey[]).map((k) => (
            <li key={k}>{t(k)}</li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

function Headline({ current, reference }: { current?: MethodSummary; reference?: MethodSummary }) {
  if (!current) return null;
  const items: { key: MessageKey; value: number | null; ref: number | null | undefined; testId: string }[] = [
    { key: "eval.kpi.recall", value: current.scenario.recall, ref: reference?.scenario.recall, testId: "kpi-recall" },
    { key: "eval.kpi.highFpr", value: current.scenario.high_band_fpr, ref: reference?.scenario.high_band_fpr, testId: "kpi-high-fpr" },
    { key: "eval.kpi.p5", value: current.queue.p_at_5, ref: reference?.queue.p_at_5, testId: "kpi-p5" },
    { key: "eval.kpi.r5", value: current.queue.recall_at_5, ref: reference?.queue.recall_at_5, testId: "kpi-r5" },
  ];
  return (
    <section aria-label={t("eval.headline")} className="grid-kpi">
      {items.map((i) => (
        <div key={i.key} className="panel kpi" data-testid={i.testId}>
          <div className="kpi__label">{t(i.key)}</div>
          <div className="kpi__value num">{pct(i.value)}</div>
          {reference && <div className="kpi__hint">{t("eval.vsV1", { value: pct(i.ref) })}</div>}
        </div>
      ))}
    </section>
  );
}

function MethodTable({ report, results }: { report: EvaluationReport; results: Record<string, MethodSummary> }) {
  const methods = report.methods.filter((m) => m.id in results);
  return (
    <div className="table-wrap">
      <table className="table table--wrap-head" data-testid="eval-methods-table">
        <caption className="visually-hidden">{t("eval.methods")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("eval.col.method")}</th>
            {(["precision", "recall", "f1", "fpr", "highFpr", "alerts", "alertPrecision", "p5", "r5", "latency"] as const).map((c) => (
              <th key={c} scope="col" className="right">
                {t(`eval.col.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {methods.map((m) => {
            const s = results[m.id]!;
            return (
              <tr key={m.id} data-emphasis={m.id === PRIMARY ? "true" : undefined}>
                <th scope="row" title={m.description}>
                  {tDynamic("eval.method.", m.id, m.label)}
                </th>
                <td className="right num">{pct(s.scenario.precision)}</td>
                <td className="right num">{pct(s.scenario.recall)}</td>
                <td className="right num">{pct(s.scenario.f1)}</td>
                <td className="right num">{pct(s.scenario.fpr)}</td>
                <td className="right num">{pct(s.scenario.high_band_fpr)}</td>
                <td className="right num">{num(s.alerts.per_dataset)}</td>
                <td className="right num">{pct(s.alerts.precision)}</td>
                <td className="right num">{pct(s.queue.p_at_5)}</td>
                <td className="right num">{pct(s.queue.recall_at_5)}</td>
                <td className="right num">{num(s.latency_ms.median)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FamilyTable({ results }: { results: Record<string, MethodSummary> }) {
  const methods = FAMILY_METHODS.filter((m) => m in results);
  const { suspicious, legitimate } = familyRows(results, methods);
  const group = (title: string, rows: FamilyRow[]) => (
    <>
      <tr className="table__group">
        <th scope="colgroup" colSpan={2 + methods.length}>
          {title}
        </th>
      </tr>
      {rows.map((r) => (
        <tr key={r.family}>
          <th scope="row">{tDynamic("family.", r.family)}</th>
          <td className="right num">{r.total}</td>
          {methods.map((m) => (
            <td key={m} className="right num">
              {r.flagged[m]}/{r.total}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
  return (
    <div className="table-wrap">
      <table className="table table--wrap-head" data-testid="eval-families-table">
        <caption className="visually-hidden">{t("eval.families")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("eval.col.family")}</th>
            <th scope="col" className="right">
              {t("eval.col.scenarios")}
            </th>
            {methods.map((m) => (
              <th key={m} scope="col" className="right">
                {tDynamic("eval.method.", m)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {group(t("eval.suspicious"), suspicious)}
          {group(t("eval.legitimate"), legitimate)}
        </tbody>
      </table>
    </div>
  );
}

function VariantTable({
  rows,
  showIdentical = false,
}: {
  rows: { label: string; summary: MethodSummary; identical?: boolean; mono?: boolean }[];
  showIdentical?: boolean;
}) {
  return (
    <div className="table-wrap">
      <table className="table table--wrap-head">
        <thead>
          <tr>
            <th scope="col">{t("eval.col.variant")}</th>
            {showIdentical && <th scope="col">{t("eval.col.identical")}</th>}
            <th scope="col" className="right">
              {t("eval.col.recall")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.fpr")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.highFpr")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.alertPrecision")}
            </th>
            <th scope="col" className="right">
              {t("eval.col.p5")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.mono ? <code className="mono">{r.label}</code> : r.label}</th>
              {showIdentical && <td>{r.identical === undefined ? "—" : r.identical ? t("common.yes") : t("common.no")}</td>}
              <td className="right num">{pct(r.summary.scenario.recall)}</td>
              <td className="right num">{pct(r.summary.scenario.fpr)}</td>
              <td className="right num">{pct(r.summary.scenario.high_band_fpr)}</td>
              <td className="right num">{pct(r.summary.alerts.precision)}</td>
              <td className="right num">{pct(r.summary.queue.p_at_5)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Examples({ report }: { report: EvaluationReport }) {
  const ex = report.examples!;
  const list = (title: string, rows: typeof ex.false_positives, testId: string) => {
    const groups = groupExamples(rows);
    return (
      <div className="stack stack--sm">
        <h3>{title}</h3>
        {groups.length === 0 ? (
          <p className="muted">{t("eval.noExamples")}</p>
        ) : (
          <div className="table-wrap">
            <table className="table table--wrap-head" data-testid={testId}>
              <thead>
                <tr>
                  <th scope="col">{t("eval.col.family")}</th>
                  <th scope="col">{t("eval.col.explanation")}</th>
                  <th scope="col">{t("eval.col.band")}</th>
                  <th scope="col" className="right">
                    {t("eval.col.cases")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <tr key={g.key}>
                    <th scope="row">
                      {tDynamic("family.", g.family)}
                      {g.kind && <div className="subtle">{tDynamic("kind.", g.kind)}</div>}
                    </th>
                    <td>{tDynamic("eval.expl.", g.explanation)}</td>
                    <td>
                      {g.bands.map((b) => tDynamic("band.", b)).join(", ") || "—"}
                      {g.priorities.length > 0 && (
                        <span className="subtle num"> · {Math.min(...g.priorities) === Math.max(...g.priorities) ? g.priorities[0] : `${Math.min(...g.priorities)}–${Math.max(...g.priorities)}`}</span>
                      )}
                    </td>
                    <td className="right num">{g.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };
  return (
    <Panel title={t("eval.examples")} hint={t("eval.examplesHint")} id="eval-examples">
      <div className="grid-2">
        {list(t("eval.fp"), ex.false_positives, "eval-fp")}
        {list(t("eval.fn"), ex.false_negatives, "eval-fn")}
      </div>
    </Panel>
  );
}
