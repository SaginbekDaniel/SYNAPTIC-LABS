import { useDeferredValue, useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { AccountId, BandBadge, bandIcon, CaseStatusBadge, Empty, ErrorState, EvidenceBadge, Icon, Loading, NoDataset, PageHeader, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { t, tDynamic } from "../../lib/i18n";
import { FORMATION_KINDS, type AlertPage, type AlertSummary } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { AlertPreview } from "./AlertPreview";
import { alertTitle, alertWhy, BAND_ORDER } from "./alertText";

type SortKey = "priority" | "accounts" | "transfers" | "recent";
const SORTS: SortKey[] = ["priority", "accounts", "transfers", "recent"];
const BAND_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, insufficient_evidence: 3, low: 4 };

function sortAlerts(items: AlertSummary[], key: SortKey): AlertSummary[] {
  const byPriority = (a: AlertSummary, b: AlertSummary) =>
    (BAND_RANK[a.risk.band] ?? 9) - (BAND_RANK[b.risk.band] ?? 9) || (b.risk.priority ?? -1) - (a.risk.priority ?? -1);
  const out = [...items];
  if (key === "priority") return out.sort(byPriority);
  if (key === "accounts") return out.sort((a, b) => b.formation.member_count - a.formation.member_count || byPriority(a, b));
  if (key === "transfers") return out.sort((a, b) => b.transaction_count - a.transaction_count || byPriority(a, b));
  return out.sort((a, b) => (a.formation.window_end < b.formation.window_end ? 1 : a.formation.window_end > b.formation.window_end ? -1 : byPriority(a, b)));
}

function matches(a: AlertSummary, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return a.formation.subject_account_id.toLowerCase().includes(needle) || alertTitle(a).toLowerCase().includes(needle);
}

export function AlertsQueue() {
  const { activeId } = useDataset();
  const navigate = useNavigate();
  const wide = useMediaQuery("(min-width: 1100px)");
  const [params, setParams] = useSearchParams();
  const band = params.get("band") ?? "";
  const kind = params.get("kind") ?? "";
  const status = params.get("status") ?? "";
  const sort = (SORTS as string[]).includes(params.get("sort") ?? "") ? (params.get("sort") as SortKey) : "priority";
  const q = params.get("q") ?? "";
  const sel = params.get("sel");
  const [draft, setDraft] = useState(q);
  const deferredQ = useDeferredValue(draft.trim());

  // Kind and status filter on the server; band, search and sort are local so band counts stay visible.
  const key = activeId ? `alerts:${activeId}:${kind}:${status}` : null;
  const alerts = useApi(key, (signal) => api.get<AlertPage>("/api/v1/alerts", { dataset_id: activeId, kind, status, limit: 200 }, signal));

  function update(changes: Record<string, string | null>, replace = true) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace });
  }

  const all = alerts.data?.items ?? [];
  const bandCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const a of all) if (matches(a, deferredQ)) c[a.risk.band] = (c[a.risk.band] ?? 0) + 1;
    return c;
  }, [all, deferredQ]);
  const visible = useMemo(
    () => sortAlerts(all.filter((a) => (!band || a.risk.band === band) && matches(a, deferredQ)), sort),
    [all, band, deferredQ, sort],
  );
  const filtered = Boolean(band || kind || status || deferredQ);
  const selected = wide && sel ? visible.find((a) => a.id === sel) ?? null : null;

  function onRowClick(e: MouseEvent, a: AlertSummary) {
    // Wide screens preview in place; modifier-clicks and narrow screens follow the link.
    if (!wide || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    update({ sel: a.id });
  }

  function onListKey(e: KeyboardEvent<HTMLUListElement>) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const links = [...e.currentTarget.querySelectorAll<HTMLAnchorElement>("[data-testid='alert-row']")];
    const i = links.indexOf(document.activeElement as HTMLAnchorElement);
    const next = links[Math.max(0, Math.min(links.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) {
      e.preventDefault();
      next.focus();
    }
  }

  return (
    <div className="page">
      <PageHeader title={t("alerts.title")} description={t("alerts.subtitle")} />
      {!activeId ? (
        <section className="panel">
          <NoDataset />
        </section>
      ) : (
        <div className={selected ? "queue queue--split" : "queue"}>
          <section className="panel queue__list" aria-labelledby="queue-title">
            <div className="toolbar">
              <h2 id="queue-title" className="visually-hidden">
                {t("alerts.title")}
              </h2>
              <form
                className="search"
                role="search"
                onSubmit={(e) => {
                  e.preventDefault();
                  update({ q: draft.trim() || null });
                }}
              >
                <Icon name="search" size={18} />
                <label className="visually-hidden" htmlFor="queue-search">
                  {t("alerts.search")}
                </label>
                <input
                  id="queue-search"
                  type="search"
                  value={draft}
                  placeholder={t("alerts.searchPlaceholder")}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    update({ q: e.target.value.trim() || null });
                  }}
                  spellCheck={false}
                  autoComplete="off"
                />
              </form>
              <div className="toolbar__filters">
                <label className="select-wrap">
                  <span className="visually-hidden">{t("alerts.filterKind")}</span>
                  <select className="select" value={kind} onChange={(e) => update({ kind: e.target.value || null, sel: null })} aria-label={t("alerts.filterKind")}>
                    <option value="">{t("alerts.allKinds")}</option>
                    {FORMATION_KINDS.map((k) => (
                      <option key={k} value={k}>
                        {tDynamic("kind.", k)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="select-wrap">
                  <span className="visually-hidden">{t("alerts.filterStatus")}</span>
                  <select className="select" value={status} onChange={(e) => update({ status: e.target.value || null, sel: null })} aria-label={t("alerts.filterStatus")}>
                    <option value="">{t("alerts.allStatuses")}</option>
                    <option value="open">{t("alerts.open")}</option>
                    <option value="in_case">{t("alerts.inCase")}</option>
                    <option value="closed">{t("alerts.closed")}</option>
                  </select>
                </label>
                <label className="select-wrap">
                  <span className="visually-hidden">{t("alerts.sort")}</span>
                  <select className="select" value={sort} onChange={(e) => update({ sort: e.target.value === "priority" ? null : e.target.value })} aria-label={t("alerts.sort")}>
                    {SORTS.map((s) => (
                      <option key={s} value={s}>
                        {t(`alerts.sort.${s}`)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
            <div className="toolbar toolbar--sub">
              <Segmented
                size="sm"
                label={t("alerts.filterBand")}
                value={band}
                onChange={(v) => update({ band: v || null, sel: null })}
                options={[
                  { value: "", label: t("alerts.all"), count: Object.values(bandCounts).reduce((a, b) => a + b, 0) },
                  ...BAND_ORDER.map((b) => ({
                    value: b,
                    label: (
                      <>
                        <Icon name={bandIcon(b)} size={14} className={`tone-${b}`} />
                        {t(`band.${b}`)}
                      </>
                    ),
                    count: bandCounts[b] ?? 0,
                  })),
                ]}
              />
              {alerts.data && (
                <span className="toolbar__count" aria-live="polite">
                  {filtered ? t("alerts.shown", { shown: visible.length, total: alerts.data.total }) : t("alerts.total", { count: alerts.data.total })}
                </span>
              )}
            </div>

            {alerts.loading && !alerts.data && (
              <div className="panel__body">
                <Loading rows={6} />
              </div>
            )}
            {alerts.error && <ErrorState error={alerts.error} onRetry={alerts.reload} />}
            {alerts.data && visible.length === 0 && (
              <Empty title={filtered ? t("alerts.emptyFiltered") : t("alerts.empty")} icon={filtered ? "search" : "supported"}>
                <p>{filtered ? t("alerts.emptyFilteredHint") : t("alerts.emptyHint")}</p>
                {filtered && (
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => {
                      setDraft("");
                      setParams(new URLSearchParams(), { replace: true });
                    }}
                  >
                    {t("alerts.resetFilters")}
                  </button>
                )}
              </Empty>
            )}
            {visible.length > 0 && (
              <ul className="alert-list" data-testid="alert-list" onKeyDown={onListKey}>
                {visible.map((a) => (
                  <li key={a.id}>
                    <AlertRow alert={a} selected={selected?.id === a.id} onClick={(e) => onRowClick(e, a)} />
                  </li>
                ))}
              </ul>
            )}
          </section>
          {selected && <AlertPreview alert={selected} onClose={() => update({ sel: null })} onOpen={() => navigate(`/alerts/${selected.id}`)} />}
        </div>
      )}
    </div>
  );
}

function AlertRow({ alert, selected, onClick }: { alert: AlertSummary; selected: boolean; onClick: (e: MouseEvent) => void }) {
  const f = alert.formation;
  const why = alertWhy(alert);
  return (
    <Link
      to={`/alerts/${alert.id}`}
      className="alert-row"
      data-testid="alert-row"
      data-band={alert.risk.band}
      aria-current={selected ? "true" : undefined}
      onClick={onClick}
    >
      <span className={`alert-row__band tone-${alert.risk.band}`} aria-hidden="true">
        <Icon name={bandIcon(alert.risk.band)} size={18} />
      </span>
      <span className="alert-row__main">
        <span className="alert-row__title">
          <span className="alert-row__name">{alertTitle(alert)}</span>
          <AccountId id={f.subject_account_id} link={false} />
        </span>
        {why && <span className="alert-row__why">{why}</span>}
        <span className="alert-row__meta">
          <span>{t("alerts.accounts", { count: f.member_count })}</span>
          <span>{t("alerts.transactions", { count: alert.transaction_count })}</span>
          <span className="num">
            {formatDate(f.window_start)} — {formatDate(f.window_end)}
          </span>
          {alert.coverage_limitations.includes("boundary_limited") && <span>{tDynamic("lim.", "boundary_limited")}</span>}
          {!alert.in_latest_snapshot && <span>{t("alerts.notInLatest")}</span>}
        </span>
      </span>
      <span className="alert-row__status">
        <BandBadge band={alert.risk.band} size="sm" />
        <span className="alert-row__priority num">{alert.risk.priority !== null ? t("alert.priorityShort", { n: alert.risk.priority }) : "—"}</span>
        <EvidenceBadge status={alert.temporal_status} />
        {alert.case_status ? <CaseStatusBadge status={alert.case_status} /> : null}
      </span>
      <Icon name="chevronRight" size={18} className="alert-row__go" />
    </Link>
  );
}
