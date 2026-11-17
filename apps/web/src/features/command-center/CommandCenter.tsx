import { Link } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { BandBadge, ErrorState, EvidenceBadge, Loading, NoDataset, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate, formatDateTime } from "../../lib/format";
import { precisionLabel, t, tDynamic } from "../../lib/i18n";
import type { Band, Overview } from "../../lib/types";
import { useApi } from "../../lib/useApi";

const BAND_ORDER: Band[] = ["critical", "high", "medium", "insufficient_evidence"];

function Kpi(props: { label: string; value: string | number; hint?: string; to?: string; testId?: string }) {
  const body = (
    <div className="panel kpi" data-testid={props.testId}>
      <div className="kpi__label">{props.label}</div>
      <div className="kpi__value num">{props.value}</div>
      {props.hint && <div className="kpi__hint">{props.hint}</div>}
    </div>
  );
  return props.to ? (
    <Link to={props.to} style={{ color: "inherit", textDecoration: "none" }}>
      {body}
    </Link>
  ) : (
    body
  );
}

export function CommandCenter() {
  const { activeId } = useDataset();
  const ov = useApi(activeId ? `overview:${activeId}` : null, (s) => api.get<Overview>(`/api/v1/datasets/${activeId}/overview`, undefined, s));

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t("command.title")}</h1>
          <p>{t("command.subtitle")}</p>
        </div>
      </div>
      {!activeId && (
        <Panel>
          <NoDataset />
        </Panel>
      )}
      {ov.loading && !ov.data && <Loading />}
      {ov.error && <ErrorState error={ov.error} onRetry={ov.reload} />}
      {ov.data && <OverviewBody ov={ov.data} />}
    </div>
  );
}

function OverviewBody({ ov }: { ov: Overview }) {
  const snap = ov.dataset.latest_snapshot;
  const openAlerts = Object.values(ov.open_alerts_by_band).reduce((a, b) => a + b, 0);
  const cases = Object.values(ov.cases_by_status).reduce((a, b) => a + b, 0);
  const formations = Object.values(ov.formations_by_kind).reduce((a, b) => a + b, 0);
  return (
    <>
      <div className="grid-kpi">
        <Kpi
          label={t("command.transactions")}
          value={snap ? snap.transactions_count : "—"}
          hint={snap ? t("command.excluded", { count: snap.excluded_count }) : t("dataset.noSnapshot")}
        />
        <Kpi label={t("command.accounts")} value={snap ? snap.nodes_count : "—"} to="/network" />
        <Kpi label={t("command.formations")} value={snap ? formations : "—"} />
        <Kpi label={t("command.openAlerts")} value={openAlerts} to="/alerts" testId="kpi-alerts" />
        <Kpi label={t("command.cases")} value={cases} to="/cases" />
      </div>
      <div className="grid-2">
        <Panel title={t("command.byBand")}>
          <div className="stack stack--sm">
            {BAND_ORDER.map((b) => (
              <Link key={b} to={`/alerts?band=${b}`} className="row" style={{ justifyContent: "space-between", color: "inherit" }}>
                <BandBadge band={b} />
                <span className="num">{ov.open_alerts_by_band[b] ?? 0}</span>
              </Link>
            ))}
          </div>
        </Panel>
        <Panel title={t("command.temporal")}>
          <div className="stack stack--sm">
            {(["supported", "possible_ambiguous", "contradicted", "unavailable"] as const).map((s) => (
              <div key={s} className="row" style={{ justifyContent: "space-between" }}>
                <EvidenceBadge status={s} />
                <span className="num">{ov.temporal_status_counts[s] ?? 0}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <Panel title={t("command.provenance")}>
        {!snap ? (
          <p className="muted">{t("dataset.noSnapshot")}</p>
        ) : (
          <dl className="kv">
            <dt>{t("command.snapshot")}</dt>
            <dd>
              <code className="mono">{snap.id}</code> · {formatDateTime(snap.computed_at)}
            </dd>
            <dt>{t("command.window")}</dt>
            <dd>{snap.window_start && snap.window_end ? `${formatDate(snap.window_start)} — ${formatDate(snap.window_end)}` : "—"}</dd>
            <dt>{t("common.precision")}</dt>
            <dd>{precisionLabel(ov.dataset.time_precision)}</dd>
            <dt>{t("command.policy")}</dt>
            <dd>
              <code className="mono">{snap.policy_version}</code> · {snap.graph_version}
            </dd>
            <dt>{t("command.inputHash")}</dt>
            <dd>
              <code className="mono">{snap.input_manifest_sha256}</code>
            </dd>
            <dt>{t("command.configHash")}</dt>
            <dd>
              <code className="mono">{snap.config_sha256}</code>
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
      </Panel>
    </>
  );
}
