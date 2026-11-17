import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { AccountId, BandBadge, bandIcon, CaseStatusBadge, Empty, ErrorState, Icon, Loading, NoDataset, PageHeader, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { t, tDynamic } from "../../lib/i18n";
import type { CasePage } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { caseTitle } from "../alerts/alertText";

type Group = "" | "active" | "final";
const FINAL = new Set(["dismissed", "closed"]);

export function CasesList() {
  const { activeId } = useDataset();
  const [params, setParams] = useSearchParams();
  const group = (["active", "final"].includes(params.get("status") ?? "") ? params.get("status") : "") as Group;
  const cases = useApi(activeId ? `cases:${activeId}` : null, (s) => api.get<CasePage>("/api/v1/cases", { dataset_id: activeId, limit: 200 }, s));
  const items = cases.data?.items ?? [];
  const counts = useMemo(() => ({ all: items.length, final: items.filter((c) => FINAL.has(c.status)).length }), [items]);
  const visible = items.filter((c) => (group === "" ? true : group === "final" ? FINAL.has(c.status) : !FINAL.has(c.status)));

  return (
    <div className="page">
      <PageHeader title={t("case.listTitle")} description={t("case.listSubtitle")} />
      <section className="panel">
        {!activeId && <NoDataset />}
        {activeId && (
          <div className="toolbar toolbar--sub">
            <Segmented
              size="sm"
              label={t("case.filter")}
              value={group}
              onChange={(v) => setParams(v ? { status: v } : {}, { replace: true })}
              options={[
                { value: "", label: t("alerts.all"), count: counts.all },
                { value: "active", label: t("case.groupActive"), count: counts.all - counts.final },
                { value: "final", label: t("case.groupFinal"), count: counts.final },
              ]}
            />
          </div>
        )}
        {cases.loading && !cases.data && (
          <div className="panel__body">
            <Loading />
          </div>
        )}
        {cases.error && <ErrorState error={cases.error} onRetry={cases.reload} />}
        {cases.data && visible.length === 0 && (
          <Empty title={items.length === 0 ? t("case.empty") : t("case.emptyGroup")} icon="cases">
            {items.length === 0 && (
              <Link to="/alerts" className="btn btn--sm">
                {t("case.toQueue")}
              </Link>
            )}
          </Empty>
        )}
        {visible.length > 0 && (
          <ul className="alert-list" data-testid="case-list">
            {visible.map((c) => {
              const { title, account } = caseTitle(c.title);
              return (
                <li key={c.id}>
                  <Link to={`/alerts/${c.alert_id}`} className="alert-row alert-row--case">
                    <span className={`alert-row__band tone-${c.band}`} aria-hidden="true">
                      <Icon name={bandIcon(c.band)} size={18} />
                    </span>
                    <span className="alert-row__main">
                      <span className="alert-row__title">
                        <span className="alert-row__name">{title}</span>
                        {account && <AccountId id={account} link={false} />}
                      </span>
                      <span className="alert-row__why">
                        {c.decision ? t("case.decisionLine", { decision: tDynamic("cs.", c.decision) }) : t("case.noDecision")}
                        {c.decision_reason && <> — {c.decision_reason}</>}
                      </span>
                      <span className="alert-row__meta">
                        <span>{t("case.openedAt", { date: formatDateTime(c.opened_at) })}</span>
                        <span>{t("case.assignedTo", { who: c.assigned_to ?? "—" })}</span>
                      </span>
                    </span>
                    <span className="alert-row__status">
                      <BandBadge band={c.band} size="sm" />
                      <CaseStatusBadge status={c.status} />
                    </span>
                    <Icon name="chevronRight" size={18} className="alert-row__go" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
