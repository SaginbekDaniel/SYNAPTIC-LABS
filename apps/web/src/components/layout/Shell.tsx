import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { signOut, useAuth } from "../../app/auth";
import { useDataset } from "../../app/dataset";
import { formatDate, formatDateTime } from "../../lib/format";
import { t, type MessageKey } from "../../lib/i18n";
import { Icon, type IconName } from "../ui/icons";
import { SimulationBadge } from "../ui";
import { ThemeSwitch } from "./ThemeSwitch";

interface NavItem {
  to: string;
  key: MessageKey;
  icon: IconName;
  end?: boolean;
}

/** Task-oriented primary navigation: understand → prioritise → investigate → review. */
const PRIMARY: NavItem[] = [
  { to: "/", key: "nav.command", icon: "overview", end: true },
  { to: "/alerts", key: "nav.alerts", icon: "queue" },
  { to: "/cases", key: "nav.cases", icon: "cases" },
  { to: "/analytics", key: "nav.analytics", icon: "analytics" },
];

/** Secondary workspace: simulation and exploration tools, out of the analyst's main path. */
const TOOLS: NavItem[] = [
  { to: "/lab", key: "nav.lab", icon: "lab" },
  { to: "/network", key: "nav.network", icon: "network" },
];

function RailLink({ item }: { item: NavItem }) {
  return (
    <NavLink to={item.to} end={item.end} className="rail__link" title={t(item.key)}>
      <Icon name={item.icon} size={20} />
      <span className="rail__text">{t(item.key)}</span>
    </NavLink>
  );
}

function DatasetContext() {
  const { list, activeId, setActiveId, active } = useDataset();
  const items = list.data?.items ?? [];
  const snap = active?.latest_snapshot;
  return (
    <div className="context">
      <label className="context__field">
        <span className="context__label">{t("dataset.label")}</span>
        <span className="context__select">
          <Icon name="database" size={16} />
          <select id="dataset-select" value={activeId ?? ""} onChange={(e) => setActiveId(e.target.value)} disabled={items.length === 0}>
            {items.length === 0 && <option value="">{t("dataset.none")}</option>}
            {items.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <Icon name="chevronDown" size={16} className="context__chevron" />
        </span>
      </label>
      {active && (
        <dl className="context__meta" data-testid="snapshot-meta">
          <div>
            <dt>{t("dataset.period")}</dt>
            <dd className="num">{snap?.window_start && snap.window_end ? `${formatDate(snap.window_start)} — ${formatDate(snap.window_end)}` : "—"}</dd>
          </div>
          <div>
            <dt>{t("dataset.analysedAt")}</dt>
            <dd className="num">{snap ? formatDateTime(snap.computed_at) : t("dataset.noSnapshot")}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/[\s._@-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function useSignOut(): [boolean, () => void] {
  const [busy, setBusy] = useState(false);
  return [
    busy,
    () => {
      if (busy) return;
      setBusy(true);
      // The route guard sends the user to the sign-in page once the store reports signed_out.
      void signOut();
    },
  ];
}

/** Signed-in identity and sign-out, at the foot of the navigation rail. */
function Account() {
  const { user } = useAuth();
  const [busy, out] = useSignOut();
  if (!user) return null;
  return (
    <div className="account" role="group" aria-label={t("account.label")} data-testid="account">
      <span className="account__avatar" aria-hidden="true" title={t("account.signedInAs", { name: user.display_name })}>
        {initials(user.display_name)}
      </span>
      <span className="account__text">
        <span className="account__name">{user.display_name}</span>
        <span className="account__id">{user.username}</span>
        <span className="account__id" data-testid="account-role">
          {t(`role.${user.role}`)}
        </span>
      </span>
      <button type="button" className="icon-btn account__out" onClick={out} disabled={busy} title={t("account.signOut")} aria-label={t("account.signOut")} data-testid="sign-out">
        <Icon name="signOut" size={18} />
      </button>
    </div>
  );
}

/** Phone overflow sheet: tools and theme, reached from the fifth tab. */
function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="sheet" role="presentation" onClick={onClose}>
      <div className="sheet__panel" role="dialog" aria-modal="true" aria-label={t("nav.more")} ref={ref} onClick={(e) => e.stopPropagation()}>
        <div className="sheet__head">
          <strong>{t("nav.tools")}</strong>
          <button type="button" className="icon-btn" onClick={onClose} aria-label={t("common.close")}>
            <Icon name="close" />
          </button>
        </div>
        <nav className="sheet__nav" aria-label={t("nav.tools")}>
          {[...TOOLS, { to: "/analytics/benchmark", key: "nav.evaluation" as MessageKey, icon: "benchmark" as IconName }].map((item) => (
            <NavLink key={item.to} to={item.to} className="sheet__link" onClick={onClose}>
              <Icon name={item.icon} size={20} />
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div className="sheet__row">
          <span>{t("theme.label")}</span>
          <ThemeSwitch />
        </div>
        <SheetAccount />
        <p className="sheet__note">{t("app.disclaimer")}</p>
      </div>
    </div>
  );
}

function SheetAccount() {
  const { user } = useAuth();
  const [busy, out] = useSignOut();
  if (!user) return null;
  return (
    <div className="sheet__row">
      <span className="sheet__who">{t("account.signedInAs", { name: user.display_name })}</span>
      <button type="button" className="btn btn--sm" onClick={out} disabled={busy} data-testid="sheet-sign-out">
        <Icon name="signOut" size={16} />
        {t("account.signOut")}
      </button>
    </div>
  );
}

export function Shell() {
  const [more, setMore] = useState(false);
  const location = useLocation();
  // Close the overflow sheet on navigation; move focus to the page for screen-reader users.
  const mainRef = useRef<HTMLElement>(null);
  const lastPath = useRef(location.pathname);
  useEffect(() => {
    setMore(false);
    // Only a real route change moves focus (StrictMode re-runs effects; the initial load must not).
    if (lastPath.current === location.pathname) return;
    lastPath.current = location.pathname;
    window.scrollTo({ top: 0 });
    mainRef.current?.focus({ preventScroll: true });
  }, [location.pathname]);
  const toolActive = TOOLS.some((i) => location.pathname.startsWith(i.to));

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        {t("nav.skip")}
      </a>
      <aside className="rail">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path d="M5 19V5l14 14V5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="brand__text">
            <span className="brand__name">{t("app.name")}</span>
            <span className="brand__team">{t("app.team")}</span>
          </span>
        </div>
        <nav className="rail__nav" aria-label={t("nav.primary")}>
          {PRIMARY.map((i) => (
            <RailLink key={i.to} item={i} />
          ))}
        </nav>
        <nav className="rail__nav rail__nav--tools" aria-label={t("nav.tools")}>
          <span className="rail__group">{t("nav.tools")}</span>
          {TOOLS.map((i) => (
            <RailLink key={i.to} item={i} />
          ))}
        </nav>
        <Account />
        <p className="rail__footer">{t("app.disclaimer")}</p>
      </aside>

      <div className="app__body">
        <header className="topbar">
          <span className="topbar__brand" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path d="M5 19V5l14 14V5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <DatasetContext />
          <div className="topbar__end">
            <SimulationBadge />
            <span className="topbar__theme">
              <ThemeSwitch />
            </span>
          </div>
        </header>
        <main className="main" id="main" ref={mainRef} tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <nav className="tabbar" aria-label={t("nav.primary")}>
        {PRIMARY.map((i) => (
          <NavLink key={i.to} to={i.to} end={i.end} className="tabbar__link">
            <Icon name={i.icon} size={22} />
            <span>{t(i.key)}</span>
          </NavLink>
        ))}
        <button type="button" className="tabbar__link" aria-expanded={more} aria-haspopup="dialog" data-active={toolActive ? "true" : undefined} onClick={() => setMore(true)}>
          <Icon name="more" size={22} />
          <span>{t("nav.more")}</span>
        </button>
      </nav>
      <MoreSheet open={more} onClose={() => setMore(false)} />
    </div>
  );
}
