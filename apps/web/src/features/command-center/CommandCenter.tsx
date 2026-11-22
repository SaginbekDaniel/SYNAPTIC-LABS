import { Link, useNavigate } from "react-router";
import { useDataset } from "../../app/dataset";
import { ActivityChart, SeriesLegend, type ActivitySeries } from "../../components/charts/ActivityChart";
import { Donut } from "../../components/charts/Donut";
import { Ring } from "../../components/charts/Progress";
import { BandBadge, bandIcon, CaseStatusBadge, Empty, ErrorState, Icon, Loading, NoDataset, PageHeader, Panel, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { t } from "../../lib/i18n";
import type { Activity, AlertPage, AlertSummary, Overview } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { alertTitle, alertWhy, BAND_COLOR, BAND_ORDER, byQueueOrder } from "../alerts/alertText";

const TOP_N = 5;

const ACTIVE_CASE = ["new", "investigating", "escalated", "reopened"];
const FINAL_CASE = ["dismissed", "closed"];

interface OverviewData {
  ov: Overview;
  activity: Activity | null;
  top: AlertSummary[];
  openCount: number;
  inCaseCount: number;
}

export function CommandCenter() {
  const { activeId, active } = useDataset();
  const snapId = active?.latest_snapshot?.id ?? null;
  // Independent reads run in parallel (one waterfall-free request group per dataset/snapshot).
  const data = useApi(activeId ? `overview:${activeId}:${snapId}` : null, async (signal) => {
    const [ov, activity, open, inCase] = await Promise.all([
      api.get<Overview>(`/api/v1/datasets/${activeId}/overview`, undefined, signal),
      snapId ? api.get<Activity>(`/api/v1/snapshots/${snapId}/activity`, undefined, signal) : Promise.resolve(null),
      api.get<AlertPage>("/api/v1/alerts", { dataset_id: activeId, status: "open", limit: TOP_N }, signal),
      api.get<AlertPage>("/api/v1/alerts", { dataset_id: activeId, status: "in_case", limit: TOP_N }, signal),
    ]);
    return {
      ov,
      activity,
      // Both lists arrive in queue order, so the first TOP_N of their merge are the top unresolved alerts.
      top: [...open.items, ...inCase.items].sort(byQueueOrder).slice(0, TOP_N),
      openCount: open.total,
      inCaseCount: inCase.total,
    } satisfies OverviewData;
  });

  return (
    <div className="page">
      {!activeId && !data.loading && (
        <>
          <PageHeader title={t("command.title")} description={t("command.subtitle")} />
          <Panel>
            <NoDataset />
          </Panel>
        </>
      )}
      {data.loading && !data.data && (
        <>
          <PageHeader title={t("command.title")} description={t("command.subtitle")} />
          <Loading rows={6} />
        </>
      )}
      {data.error && <ErrorState error={data.error} onRetry={data.reload} />}
      {data.data && <OverviewBody d={data.data} />}
    </div>
  );
}

function OverviewBody({ d }: { d: OverviewData }) {
  const navigate = useNavigate();
  const { ov } = d;
  const snap = ov.dataset.latest_snapshot;
  const bandCounts = ov.open_alerts_by_band;
  const openAlerts = Object.values(bandCounts).reduce((a, b) => a + b, 0);
  const cases = Object.values(ov.cases_by_status).reduce((a, b) => a + b, 0);
  const sumOf = (keys: string[]) => keys.reduce((a, k) => a + (ov.cases_by_status[k] ?? 0), 0);
  const activeCases = sumOf(ACTIVE_CASE);
  const finalCases = sumOf(FINAL_CASE);
  const lead = d.top[0];

  const statusLine = !snap
    ? t("dataset.noSnapshot")
    : d.openCount > 0
      ? t("command.next", { count: d.openCount })
      : openAlerts > 0
        ? t("command.allTaken")
        : t("command.nothing");

  return (
    <>
      <PageHeader
        title={t("command.title")}
        description={statusLine}
        actions={
          lead ? (
            <Link className="btn btn--primary btn--lg" to={`/alerts/${lead.id}`} data-testid="lead-action">
              {t("command.openLead")}
              <Icon name="arrowRight" size={18} />
            </Link>
          ) : (
            <Link className="btn btn--lg" to="/lab">
              <Icon name="lab" size={18} />
              {t("state.toLab")}
            </Link>
          )
        }
      />

      <section className="kpi-strip" aria-label={t("command.kpis")}>
        <Stat
          icon="bandHigh"
          tone="accent"
          label={t("command.kpi.suspicious")}
          value={openAlerts}
          hint={t("command.kpi.suspiciousHint")}
          to="/alerts"
          testId="kpi-alerts"
        />
        <Stat icon="queue" tone="cyan" label={t("command.kpi.toReview")} value={d.openCount} hint={t("command.kpi.toReviewHint")} to="/alerts?status=open" />
        <Stat icon="cases" tone="pink" label={t("command.kpi.active")} value={activeCases} hint={t("command.kpi.activeHint")} to="/cases" />
        <Stat icon="supported" tone="green" label={t("command.kpi.reviewed")} value={finalCases} hint={t("command.kpi.reviewedHint")} to="/cases?status=final" />
      </section>

      <div className="overview-grid">
        <ActivityPanel activity={d.activity} />

        <Panel title={t("command.byBand")} hint={t("command.byBandHint")} id="risk" className="overview-grid__risk">
          {openAlerts === 0 ? (
            <Empty title={t("command.noAlerts")} icon="supported" />
          ) : (
            <Donut
              label={t("command.byBand")}
              centerValue={openAlerts}
              centerLabel={t("command.alertsWord", { count: openAlerts })}
              segments={BAND_ORDER.map((b) => ({ key: b, label: t(`band.${b}`), value: bandCounts[b] ?? 0, color: BAND_COLOR[b], icon: bandIcon(b) }))}
              onSelect={(b) => navigate(`/alerts?band=${b}`)}
            />
          )}
        </Panel>

        <Panel
          title={t("command.priority")}
          hint={t("command.priorityHint")}
          id="priority"
          className="overview-grid__priority"
          actions={
            <Link to="/alerts" className="btn btn--sm btn--ghost">
              {t("command.allAlerts")}
              <Icon name="chevronRight" size={16} />
            </Link>
          }
          flush
        >
          {d.top.length === 0 ? (
            <Empty title={t("command.noAlerts")} icon="supported" />
          ) : (
            <ol className="priority-list">
              {d.top.map((a) => (
                <li key={a.id}>
                  <Link to={`/alerts/${a.id}`} className="priority-item" data-band={a.risk.band}>
                    <span className={`priority-item__icon tone-${a.risk.band}`}>
                      <Icon name={bandIcon(a.risk.band)} size={18} />
                    </span>
                    <span className="priority-item__main">
                      <span className="priority-item__title">{alertTitle(a)}</span>
                      <span className="priority-item__why">{alertWhy(a)}</span>
                    </span>
                    <span className="priority-item__meta">
                      <BandBadge band={a.risk.band} size="sm" />
                      {a.case_status ? <CaseStatusBadge status={a.case_status} /> : <span className="badge badge--tone-pending badge--case">{t("alerts.open")}</span>}
                    </span>
                    <Icon name="chevronRight" size={18} className="priority-item__go" />
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <Panel title={t("command.progress")} hint={t("command.progressHint")} id="progress" className="overview-grid__progress">
          <div className="ring-row">
            <Ring
              value={d.inCaseCount}
              total={openAlerts}
              label={t("command.ring.taken")}
              detail={t("command.ring.takenDetail", { value: d.inCaseCount, total: openAlerts })}
              color="var(--cyan)"
            />
            <Ring
              value={activeCases}
              total={cases}
              label={t("command.ring.awaiting")}
              detail={cases ? t("command.ring.casesDetail", { value: activeCases, total: cases }) : t("command.ring.noCases")}
              color="var(--accent)"
            />
            <Ring
              value={finalCases}
              total={cases}
              label={t("command.ring.done")}
              detail={cases ? t("command.ring.casesDetail", { value: finalCases, total: cases }) : t("command.ring.noCases")}
              color="var(--ev-supported)"
            />
          </div>
        </Panel>
      </div>

      {snap?.is_partial && <div className="callout callout--warn">{t("command.partial", { reasons: snap.partial_reasons.join(", ") })}</div>}
      <p className="page-foot">
        {t("command.source", { name: ov.dataset.name })}{" "}
        <Link to="/analytics">{t("command.toDiagnostics")}</Link>
      </p>
    </>
  );
}

const SERIES: ActivitySeries[] = [
  { key: "transactions", label: t("command.series.all"), color: "var(--accent)", kind: "area" },
  { key: "in_alerts", label: t("command.series.alerts"), color: "var(--cyan)", kind: "line" },
];

function ActivityPanel({ activity }: { activity: Activity | null }) {
  const days = activity?.days ?? [];
  const total = days.reduce((a, d) => a + d.transactions, 0);
  const cited = days.reduce((a, d) => a + d.in_alerts, 0);
  return (
    <Panel title={t("command.activity")} hint={t("command.activityHint")} id="activity" className="overview-grid__activity" actions={<SeriesLegend series={SERIES} />}>
      {!activity || days.length === 0 ? (
        <Empty title={t("dataset.noSnapshot")} icon="calendar" />
      ) : (
        <div className="activity">
          <div className="activity__figures">
            <div>
              <span className="figure num">{total.toLocaleString("ru-RU")}</span>
              <span className="figure__label">{t("command.figure.transfers", { count: total })}</span>
            </div>
            <div>
              <span className="figure figure--secondary num">{cited.toLocaleString("ru-RU")}</span>
              <span className="figure__label">
                {t("command.figure.cited")}
                {total > 0 && <span className="num"> · {Math.round((cited / total) * 100)} %</span>}
              </span>
            </div>
            <div className="activity__period">
              <Icon name="calendar" size={16} />
              <span className="num">
                {formatDate(days[0]!.date)} — {formatDate(days[days.length - 1]!.date)}
              </span>
              <span className="activity__precision">{t("command.dayPrecision")}</span>
            </div>
          </div>
          <ActivityChart
            caption={t("command.activity")}
            unit={t("command.activityUnit")}
            series={SERIES}
            points={days.map((d) => ({ date: d.date, values: { transactions: d.transactions, in_alerts: d.in_alerts } }))}
          />
        </div>
      )}
    </Panel>
  );
}
