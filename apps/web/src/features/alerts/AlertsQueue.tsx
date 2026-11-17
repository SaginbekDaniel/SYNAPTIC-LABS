import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
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
/** Server page size. Band counts, totals, search and sorting are computed over all matches by the API. */
export const QUEUE_PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 250;

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
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const [draft, setDraft] = useState(q);

  // Keep the field in sync when the URL changes from outside (back/forward, reset).
  const lastUrlQ = useRef(q);
  useEffect(() => {
    if (q !== lastUrlQ.current) {
      lastUrlQ.current = q;
      setDraft(q);
    }
  }, [q]);

  // Every filter, the search and the sort run on the server; the queue only ever holds one page.
  const key = activeId ? `alerts:${activeId}:${band}:${kind}:${status}:${q}:${sort}:${page}` : null;
  const alerts = useApi(
    key,
    (signal) =>
      api.get<AlertPage>(
        "/api/v1/alerts",
        { dataset_id: activeId, band, kind, status, q, sort, limit: QUEUE_PAGE_SIZE, offset: (page - 1) * QUEUE_PAGE_SIZE },
        signal,
      ),
    { scope: activeId ?? undefined },
  );

  function update(changes: Record<string, string | null>, replace = true) {
    const next = new URLSearchParams(params);
    // Any change to what is listed starts again from the first page.
    if (!("page" in changes) && !("sel" in changes && Object.keys(changes).length === 1)) next.delete("page");
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace });
  }

  useEffect(() => {
    const trimmed = draft.trim();
    if (trimmed === q) return;
    const id = window.setTimeout(() => {
      lastUrlQ.current = trimmed;
      update({ q: trimmed || null, sel: null });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
    // `update` closes over the current params; re-arming on every params change would reset the timer.
  }, [draft, q]); // eslint-disable-line react-hooks/exhaustive-deps

  const pageData = alerts.data;
  const visible = pageData?.items ?? [];
  const bandCounts = pageData?.band_counts ?? {};
  const total = pageData?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / QUEUE_PAGE_SIZE));
  const from = pageData && total > 0 ? pageData.offset + 1 : 0;
  const to = pageData ? pageData.offset + visible.length : 0;
  const filtered = Boolean(band || kind || status || q);
  const refreshing = alerts.loading && pageData !== null;
  const selected = wide && sel ? visible.find((a) => a.id === sel) ?? null : null;

  // A page beyond the end (e.g. after a filter shrank the list in another tab) falls back to the last page.
  useEffect(() => {
    if (pageData && page > pageCount) update({ page: pageCount > 1 ? String(pageCount) : null });
  }, [pageData, page, pageCount]); // eslint-disable-line react-hooks/exhaustive-deps

  function goToPage(n: number) {
    update({ page: n > 1 ? String(n) : null, sel: null }, false);
    document.getElementById("queue-title")?.scrollIntoView({ block: "nearest" });
  }

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
                  lastUrlQ.current = draft.trim();
                  update({ q: draft.trim() || null, sel: null });
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
                  onChange={(e) => setDraft(e.target.value)}
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
              {pageData && (
                <span className="toolbar__count num" aria-live="polite" data-testid="queue-count">
                  {total === 0
                    ? t("alerts.total", { count: 0 })
                    : pageCount > 1
                      ? t(filtered ? "alerts.rangeFiltered" : "alerts.range", { from, to, total })
                      : t(filtered ? "alerts.found" : "alerts.total", { count: total })}
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
                      lastUrlQ.current = "";
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
              <ul className="alert-list" data-testid="alert-list" onKeyDown={onListKey} aria-busy={refreshing || undefined} data-refreshing={refreshing || undefined}>
                {visible.map((a) => (
                  <li key={a.id}>
                    <AlertRow alert={a} selected={selected?.id === a.id} onClick={(e) => onRowClick(e, a)} />
                  </li>
                ))}
              </ul>
            )}
            {pageData && pageCount > 1 && <Pager page={Math.min(page, pageCount)} pageCount={pageCount} onPage={goToPage} disabled={refreshing} />}
          </section>
          {selected && <AlertPreview alert={selected} onClose={() => update({ sel: null })} onOpen={() => navigate(`/alerts/${selected.id}`)} />}
        </div>
      )}
    </div>
  );
}

function Pager({ page, pageCount, onPage, disabled }: { page: number; pageCount: number; onPage: (n: number) => void; disabled: boolean }) {
  return (
    <nav className="pager" aria-label={t("alerts.pager")}>
      <button type="button" className="btn btn--sm" disabled={disabled || page <= 1} onClick={() => onPage(page - 1)}>
        <Icon name="arrowLeft" size={16} />
        {t("alerts.prevPage")}
      </button>
      <span className="pager__status num" aria-current="page">
        {t("alerts.pageOf", { page, pages: pageCount })}
      </span>
      <button type="button" className="btn btn--sm" disabled={disabled || page >= pageCount} onClick={() => onPage(page + 1)} data-testid="next-page">
        {t("alerts.nextPage")}
        <Icon name="arrowRight" size={16} />
      </button>
    </nav>
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
