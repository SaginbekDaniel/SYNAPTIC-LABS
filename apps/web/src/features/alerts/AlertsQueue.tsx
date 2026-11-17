import { Link, useSearchParams } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { AccountId, BandBadge, CaseStatusBadge, Empty, ErrorState, EvidenceBadge, Loading, NoDataset, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { reasonText, t, tDynamic } from "../../lib/i18n";
import type { AlertPage, AlertSummary, Band } from "../../lib/types";
import { useApi } from "../../lib/useApi";

const BANDS: Band[] = ["critical", "high", "medium", "insufficient_evidence"];

export function AlertsQueue() {
  const { activeId } = useDataset();
  const [params, setParams] = useSearchParams();
  const band = params.get("band") ?? "";
  const kind = params.get("kind") ?? "";
  const status = params.get("status") ?? "";
  const key = activeId ? `alerts:${activeId}:${band}:${kind}:${status}` : null;
  const alerts = useApi(key, (signal) =>
    api.get<AlertPage>("/api/v1/alerts", { dataset_id: activeId, band: band ? [band] : undefined, kind, status, limit: 200 }, signal),
  );

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t("alerts.title")}</h1>
          <p>{t("alerts.subtitle")}</p>
        </div>
      </div>
      {!activeId ? (
        <Panel>
          <NoDataset />
        </Panel>
      ) : (
        <Panel
          flush
          title={alerts.data ? t("alerts.total", { count: alerts.data.total }) : t("alerts.title")}
          actions={
            <>
              <label className="field">
                <span className="visually-hidden">{t("alerts.filterBand")}</span>
                <select className="select" value={band} onChange={(e) => setFilter("band", e.target.value)} aria-label={t("alerts.filterBand")}>
                  <option value="">{`${t("alerts.filterBand")}: ${t("alerts.all")}`}</option>
                  {BANDS.map((b) => (
                    <option key={b} value={b}>
                      {t(`band.${b}`)}
                    </option>
                  ))}
                </select>
              </label>
              <select className="select" value={kind} onChange={(e) => setFilter("kind", e.target.value)} aria-label={t("alerts.filterKind")}>
                <option value="">{`${t("alerts.filterKind")}: ${t("alerts.all")}`}</option>
                <option value="funnel">{t("kind.funnel")}</option>
                <option value="chain">{t("kind.chain")}</option>
              </select>
              <select className="select" value={status} onChange={(e) => setFilter("status", e.target.value)} aria-label={t("alerts.filterStatus")}>
                <option value="">{`${t("alerts.filterStatus")}: ${t("alerts.all")}`}</option>
                <option value="open">{t("alerts.open")}</option>
                <option value="in_case">{t("alerts.inCase")}</option>
                <option value="closed">{t("alerts.closed")}</option>
              </select>
            </>
          }
        >
          {alerts.loading && !alerts.data && (
            <div className="panel__body">
              <Loading />
            </div>
          )}
          {alerts.error && <ErrorState error={alerts.error} onRetry={alerts.reload} />}
          {alerts.data && alerts.data.items.length === 0 && (
            <Empty title={t("alerts.empty")}>
              <span>{t("alerts.emptyHint")}</span>
            </Empty>
          )}
          {alerts.data && alerts.data.items.length > 0 && (
            <ul className="alert-list" data-testid="alert-list">
              {alerts.data.items.map((a) => (
                <li key={a.id}>
                  <AlertRow alert={a} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}
    </div>
  );
}

function AlertRow({ alert }: { alert: AlertSummary }) {
  const f = alert.formation;
  const structural = alert.risk.reason_codes.find((r) => r.code.startsWith("STRUCT_"));
  return (
    <Link to={`/alerts/${alert.id}`} className="alert-row" data-testid="alert-row" data-band={alert.risk.band}>
      <div className="priority">
        <BandBadge band={alert.risk.band} />
        <span className="priority__value">
          {alert.risk.priority !== null ? `${t("alert.priority")} ${alert.risk.priority}` : "—"}
        </span>
      </div>
      <div className="stack stack--sm" style={{ minWidth: 0 }}>
        <div className="alert-row__title">
          {t(f.kind === "funnel" ? "kind.funnel" : "kind.chain")} · <AccountId id={f.subject_account_id} link={false} />
        </div>
        {structural && <span className="subtle">{reasonText(structural, f.currency)}</span>}
        <div className="alert-row__meta">
          <span>{t("alerts.accounts", { count: f.member_count })}</span>
          <span>{t("alerts.transactions", { count: alert.transaction_count })}</span>
          <span>
            {formatDate(f.window_start)} — {formatDate(f.window_end)}
          </span>
          {alert.coverage_limitations.includes("timestamp_precision_limited") && <span>{t("common.precisionDay")}</span>}
          {alert.coverage_limitations.includes("boundary_limited") && <span>{tDynamic("lim.", "boundary_limited")}</span>}
          {!alert.in_latest_snapshot && <span>{t("alerts.notInLatest")}</span>}
        </div>
      </div>
      <div className="row alert-row__badges">
        <EvidenceBadge status={alert.temporal_status} />
        {alert.case_status && <CaseStatusBadge status={alert.case_status} />}
      </div>
    </Link>
  );
}
