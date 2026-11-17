import { useState } from "react";
import { BarList } from "../../components/charts/Progress";
import { Disclosure, Empty, ErrorState, Icon, Loading, PageHeader, Panel, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime, shortId } from "../../lib/format";
import { t, tDynamic, type MessageKey } from "../../lib/i18n";
import type { EvaluationReport, MethodSummary } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { AnalyticsTabs } from "../analytics/AnalyticsTabs";
import { defaultSplit, familyRows, groupExamples, num, pct, SPLIT_ORDER, type FamilyRow } from "./evaluationView";

const PRIMARY = "nexora_v2";
const REFERENCE = "nexora_v1";
const FAMILY_METHODS = [PRIMARY, REFERENCE, "B1_rules"] as const;

export function Evaluation() {
  const report = useApi("evaluation", (s) => api.get<EvaluationReport>("/api/v1/evaluation", undefined, s));
  return (
    <div className="page">
      <PageHeader title={t("eval.title")} description={t("eval.subtitle")} />
      <AnalyticsTabs />
      <div className="callout callout--warn" role="note">
        <Icon name="info" size={16} />
        {t("eval.synthetic")}
      </div>
      {report.loading && !report.data && <Loading rows={8} />}
      {report.error?.code === "BENCHMARK_NOT_FOUND" ? (
        <Panel>
          <Empty title={t("eval.emptyTitle")} icon="benchmark">
            <p>{t("eval.emptyBody")}</p>
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

type CompareMetric = "recall" | "alertPrecision" | "p5" | "highFpr";
const COMPARE: Record<CompareMetric, { get: (s: MethodSummary) => number | null; lowerIsBetter?: boolean }> = {
  recall: { get: (s) => s.scenario.recall },
  alertPrecision: { get: (s) => s.alerts.precision },
  p5: { get: (s) => s.queue.p_at_5 },
  highFpr: { get: (s) => s.scenario.high_band_fpr, lowerIsBetter: true },
};

function EvaluationBody({ report }: { report: EvaluationReport }) {
  const [split, setSplit] = useState<string | null>(() => defaultSplit(report));
  const [metric, setMetric] = useState<CompareMetric>("recall");
  const available = SPLIT_ORDER.filter((s) => s in report.results);
  const results = split ? report.results[split] : undefined;
  const info = split ? report.splits[split] : undefined;
  if (!split || !results) return null;
  const methods = report.methods.filter((m) => m.id in results);
  const cmp = COMPARE[metric];
  return (
    <>
      <div className="split-bar">
        <Segmented
          label={t("eval.split")}
          value={split}
          onChange={setSplit}
          options={available.map((s) => ({ value: s, label: tDynamic("eval.split.", s) }))}
        />
        {info && (
          <span className="split-bar__meta" data-testid="split-meta">
            {t("eval.splitMeta", { datasets: info.datasets, from: info.seeds[0] ?? 0, to: info.seeds[1] ?? 0 })} · {tDynamic("eval.splitRole.", split)}
          </span>
        )}
      </div>

      <Headline current={results[PRIMARY]} reference={results[REFERENCE]} />

      <div className="eval-grid">
        <Panel
          title={t("eval.compare")}
          hint={cmp.lowerIsBetter ? t("eval.compareLower") : t("eval.compareHigher")}
          id="eval-compare"
        >
          <div className="compare-switch">
            <Segmented
              size="sm"
              label={t("eval.compareMetric")}
              value={metric}
              onChange={setMetric}
              options={(Object.keys(COMPARE) as CompareMetric[]).map((k) => ({ value: k, label: t(`eval.short.${k}`) }))}
            />
          </div>
          <BarList
            max={1}
            scaleLabel={t("eval.scalePct")}
            rows={methods.map((m) => {
              const v = cmp.get(results[m.id]!);
              return {
                key: m.id,
                label: tDynamic("eval.method.", m.id, m.label),
                value: v ?? 0,
                display: pct(v),
                color: m.id === PRIMARY ? "var(--accent)" : m.id === REFERENCE ? "var(--cyan)" : "var(--neutral-series)",
                note: v === null ? t("eval.notApplicable") : undefined,
              };
            })}
          />
        </Panel>
        <FamilyChart results={results} />
      </div>

      <Panel title={t("eval.methods")} hint={t("eval.methodsHint")} flush id="eval-methods">
        <MethodTable report={report} results={results} />
      </Panel>

      {report.examples && <Examples report={report} />}

      <Disclosure summary={t("eval.experiments")}>
        <div className="stack-lg">
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
        </div>
      </Disclosure>

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
              <span className="cell-note">· {report.code.dirty ? t("eval.run.dirty") : t("eval.run.clean")}</span>
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

/** Per scenario family: share of networks flagged by v2, with v1 as a reference tick. */
function FamilyChart({ results }: { results: Record<string, MethodSummary> }) {
  const methods = FAMILY_METHODS.filter((m) => m in results);
  const { suspicious, legitimate } = familyRows(results, methods);
  const row = (r: FamilyRow, color: string) => {
    const share = r.total ? r.flagged[PRIMARY]! / r.total : 0;
    const ref = REFERENCE in results && r.total ? r.flagged[REFERENCE]! / r.total : null;
    return {
      key: r.family,
      // The group heading already says suspicious/legitimate; drop the repeated suffix.
      label: tDynamic("family.", r.family).replace(/\s*\([^)]*\)$/, ""),
      value: share,
      display: `${r.flagged[PRIMARY]}/${r.total}`,
      color,
      reference: ref !== null ? { value: ref, label: t("eval.vsV1", { value: `${r.flagged[REFERENCE]}/${r.total}` }) } : undefined,
    };
  };
  return (
    <Panel title={t("eval.familyChart")} hint={t("eval.familyChartHint")} id="eval-family-chart">
      <h3 className="ctx__label ctx__label--supports">{t("eval.suspiciousFound")}</h3>
      <BarList max={1} rows={suspicious.map((r) => row(r, "var(--accent)"))} />
      <h3 className="ctx__label ctx__label--weakens">{t("eval.legitimateFlagged")}</h3>
      <BarList max={1} rows={legitimate.map((r) => row(r, "var(--pink)"))} />
    </Panel>
  );
}

function Headline({ current, reference }: { current?: MethodSummary; reference?: MethodSummary }) {
  if (!current) return null;
  const items: { key: MessageKey; value: number | null; ref: number | null | undefined; testId: string; lower?: boolean }[] = [
    { key: "eval.kpi.recall", value: current.scenario.recall, ref: reference?.scenario.recall, testId: "kpi-recall" },
    { key: "eval.kpi.highFpr", value: current.scenario.high_band_fpr, ref: reference?.scenario.high_band_fpr, testId: "kpi-high-fpr", lower: true },
    // Distinct planted networks among the first five alerts: a second alert on an already found network is
    // not a new find (audit L-02). Artifacts written before that metric fall back to raw P@5.
    current.queue.distinct_p_at_5 != null
      ? { key: "eval.kpi.p5Distinct", value: current.queue.distinct_p_at_5, ref: reference?.queue.distinct_p_at_5, testId: "kpi-p5" }
      : { key: "eval.kpi.p5", value: current.queue.p_at_5, ref: reference?.queue.p_at_5, testId: "kpi-p5" },
    { key: "eval.kpi.r5", value: current.queue.recall_at_5, ref: reference?.queue.recall_at_5, testId: "kpi-r5" },
  ];
  return (
    <section aria-label={t("eval.headline")} className="kpi-strip">
      {items.map((i) => (
        <div key={i.key} className="stat stat--metric" data-testid={i.testId}>
          <div className="stat__label">{t(i.key)}</div>
          <div className="stat__value num">{pct(i.value)}</div>
          <div className="metric-bar" aria-hidden="true">
            <span className="metric-bar__fill" data-lower={i.lower ? "true" : undefined} style={{ width: `${(i.value ?? 0) * 100}%` }} />
            {typeof i.ref === "number" && <span className="metric-bar__ref" style={{ left: `${i.ref * 100}%` }} />}
          </div>
          {reference && (
            <div className="stat__hint">
              {t("eval.vsV1", { value: pct(i.ref) })}
              {i.lower && <span> · {t("eval.lowerBetter")}</span>}
            </div>
          )}
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
      <div className="lab-block">
        <h3 className="ctx__label">{title}</h3>
        {groups.length === 0 ? (
          <p className="ctx__note">{t("eval.noExamples")}</p>
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
                      {g.kind && <div className="cell-note">{tDynamic("kind.", g.kind)}</div>}
                    </th>
                    <td>{tDynamic("eval.expl.", g.explanation)}</td>
                    <td>
                      {g.bands.map((b) => tDynamic("band.", b)).join(", ") || "—"}
                      {g.priorities.length > 0 && (
                        <span className="cell-note num"> · {Math.min(...g.priorities) === Math.max(...g.priorities) ? g.priorities[0] : `${Math.min(...g.priorities)}–${Math.max(...g.priorities)}`}</span>
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
