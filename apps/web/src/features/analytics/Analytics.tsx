import { useNavigate } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { Donut } from "../../components/charts/Donut";
import { BarList, ColumnChart } from "../../components/charts/Progress";
import { Disclosure, Empty, ErrorState, Loading, NoDataset, PageHeader, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate, formatDateTime } from "../../lib/format";
import { precisionLabel, t, tDynamic } from "../../lib/i18n";
import { FORMATION_KINDS, type AlertPage, type Overview } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { BAND_COLOR, BAND_ORDER } from "../alerts/alertText";
import { AnalyticsTabs } from "./AnalyticsTabs";

const KIND_COLOR: Record<string, string> = { funnel: "var(--accent)", fan_out: "var(--pink)", chain: "var(--cyan)", cycle: "var(--band-medium)" };
const TEMPORAL = ["supported", "possible_ambiguous", "contradicted", "unavailable"] as const;
const TEMPORAL_ICON = { supported: "supported", possible_ambiguous: "ambiguous", contradicted: "contradicted", unavailable: "unavailable" } as const;
const TEMPORAL_COLOR = {
  supported: "var(--ev-supported)",
  possible_ambiguous: "var(--ev-ambiguous)",
  contradicted: "var(--ev-contradicted)",
  unavailable: "var(--ev-unavailable)",
};
const CASE_ORDER = ["new", "investigating", "escalated", "reopened", "dismissed", "closed"];
const CASE_COLOR: Record<string, string> = {
  new: "var(--cyan)",
  investigating: "var(--accent)",
  escalated: "var(--band-high)",
  reopened: "var(--pink)",
  dismissed: "var(--neutral-series)",
  closed: "var(--ev-supported)",
};

export function Analytics() {
  const { activeId } = useDataset();
  const navigate = useNavigate();
  const data = useApi(activeId ? `analytics:${activeId}` : null, async (signal) => {
    const [ov, alerts] = await Promise.all([
      api.get<Overview>(`/api/v1/datasets/${activeId}/overview`, undefined, signal),
      // Only the facet counts are needed: they cover every alert in the dataset, not just one page.
      api.get<AlertPage>("/api/v1/alerts", { dataset_id: activeId, limit: 1 }, signal),
    ]);
    return { ov, alerts };
  });

  return (
    <div className="page">
      <PageHeader title={t("analytics.title")} description={t("analytics.subtitle")} />
      <AnalyticsTabs />
      {!activeId && (
        <Panel>
          <NoDataset />
        </Panel>
      )}
      {data.loading && !data.data && <Loading rows={6} />}
      {data.error && <ErrorState error={data.error} onRetry={data.reload} />}
      {data.data &&
        (() => {
          const { ov, alerts } = data.data;
          const snap = ov.dataset.latest_snapshot;
          const formations = Object.values(ov.formations_by_kind).reduce((a, b) => a + b, 0);
          const alertsByKind = alerts.kind_counts ?? {};
          const temporalTotal = TEMPORAL.reduce((a, s) => a + (ov.temporal_status_counts[s] ?? 0), 0);
          const cases = Object.values(ov.cases_by_status).reduce((a, b) => a + b, 0);
          const maxKind = Math.max(1, ...FORMATION_KINDS.map((k) => ov.formations_by_kind[k] ?? 0));
          return (
            <div className="analytics-grid">
              <Panel title={t("analytics.kinds")} hint={t("analytics.kindsHint", { count: formations })} className="analytics-grid__wide">
                <BarList
                  max={maxKind}
                  scaleLabel={t("analytics.kindsScale")}
                  rows={FORMATION_KINDS.map((k) => ({
                    key: k,
                    label: tDynamic("kind.", k),
                    value: ov.formations_by_kind[k] ?? 0,
                    display: String(ov.formations_by_kind[k] ?? 0),
                    color: KIND_COLOR[k],
                    note: t("analytics.kindAlerts", { count: alertsByKind[k] ?? 0 }),
                  }))}
                />
              </Panel>

              <Panel title={t("analytics.temporal")} hint={t("analytics.temporalHint")}>
                {temporalTotal === 0 ? (
                  <Empty title={t("dataset.noSnapshot")} />
                ) : (
                  <Donut
                    label={t("analytics.temporal")}
                    centerValue={temporalTotal}
                    centerLabel={t("analytics.formationsWord", { count: temporalTotal })}
                    segments={TEMPORAL.map((s) => ({ key: s, label: tDynamic("ev.", s), value: ov.temporal_status_counts[s] ?? 0, color: TEMPORAL_COLOR[s], icon: TEMPORAL_ICON[s] }))}
                  />
                )}
              </Panel>

              <Panel title={t("analytics.bands")} hint={t("analytics.bandsHint")}>
                <ColumnChart
                  label={t("analytics.bands")}
                  columns={BAND_ORDER.map((b) => ({ key: b, label: t(`band.${b}`), value: ov.open_alerts_by_band[b] ?? 0, color: BAND_COLOR[b] }))}
                />
                <div className="column-links">
                  {BAND_ORDER.map((b) => (
                    <button key={b} type="button" className="link-btn" onClick={() => navigate(`/alerts?band=${b}`)}>
                      {t("analytics.openBand", { band: t(`band.${b}`) })}
                    </button>
                  ))}
                </div>
              </Panel>

              <Panel title={t("analytics.cases")} hint={t("analytics.casesHint")}>
                {cases === 0 ? (
                  <Empty title={t("command.ring.noCases")} icon="cases" />
                ) : (
                  <Donut
                    label={t("analytics.cases")}
                    centerValue={cases}
                    centerLabel={t("analytics.casesWord", { count: cases })}
                    segments={CASE_ORDER.filter((s) => (ov.cases_by_status[s] ?? 0) > 0).map((s) => ({ key: s, label: tDynamic("cs.", s), value: ov.cases_by_status[s] ?? 0, color: CASE_COLOR[s]! }))}
                  />
                )}
              </Panel>

              <div className="analytics-grid__wide">
                <Disclosure summary={t("analytics.diagnostics")} id="diagnostics">
                  {!snap ? (
                    <p className="ctx__note">{t("dataset.noSnapshot")}</p>
                  ) : (
                    <dl className="kv">
                      <dt>{t("command.snapshot")}</dt>
                      <dd>
                        <code className="mono">{snap.id}</code> · {formatDateTime(snap.computed_at)}
                      </dd>
                      <dt>{t("command.window")}</dt>
                      <dd>{snap.window_start && snap.window_end ? `${formatDate(snap.window_start)} — ${formatDate(snap.window_end)}` : "—"}</dd>
                      <dt>{t("analytics.graphSize")}</dt>
                      <dd className="num">{t("analytics.graphSizeValue", { nodes: snap.nodes_count, edges: snap.edges_count, tx: snap.transactions_count })}</dd>
                      <dt>{t("analytics.excluded")}</dt>
                      <dd className="num">{t("analytics.excludedValue", { excluded: snap.excluded_count, quarantined: snap.quarantined_count })}</dd>
                      <dt>{t("common.precision")}</dt>
                      <dd>{precisionLabel(ov.dataset.time_precision)}</dd>
                      <dt>{t("command.policy")}</dt>
                      <dd>
                        <code className="mono">{snap.policy_version}</code> · {snap.graph_version}
                      </dd>
                      <dt>{t("command.inputHash")}</dt>
                      <dd>
                        <code className="mono hash">{snap.input_manifest_sha256}</code>
                      </dd>
                      <dt>{t("command.configHash")}</dt>
                      <dd>
                        <code className="mono hash">{snap.config_sha256}</code>
                      </dd>
                      {ov.dataset.latest_job && (
                        <>
                          <dt>{t("command.job")}</dt>
                          <dd>{tDynamic("job.", ov.dataset.latest_job.status)}</dd>
                        </>
                      )}
                    </dl>
                  )}
                  {snap?.is_partial && <div className="callout callout--warn">{t("command.partial", { reasons: snap.partial_reasons.join(", ") })}</div>}
                </Disclosure>
              </div>
            </div>
          );
        })()}
    </div>
  );
}
