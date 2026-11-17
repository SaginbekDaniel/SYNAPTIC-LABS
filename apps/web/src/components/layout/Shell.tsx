import { NavLink, Outlet } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { formatDateTime, shortId } from "../../lib/format";
import { t, type MessageKey } from "../../lib/i18n";
import { SimulationBadge } from "../ui";

const NAV: { to: string; key: MessageKey; end?: boolean }[] = [
  { to: "/", key: "nav.command", end: true },
  { to: "/alerts", key: "nav.alerts" },
  { to: "/cases", key: "nav.cases" },
  { to: "/network", key: "nav.network" },
  { to: "/lab", key: "nav.lab" },
];

function NavItems() {
  return (
    <>
      {NAV.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end} className="nav-link">
          {t(item.key)}
        </NavLink>
      ))}
    </>
  );
}

function DatasetSelect() {
  const { list, activeId, setActiveId, active } = useDataset();
  const items = list.data?.items ?? [];
  const snap = active?.latest_snapshot;
  return (
    <div className="topbar__context">
      <label className="visually-hidden" htmlFor="dataset-select">
        {t("dataset.label")}
      </label>
      <select
        id="dataset-select"
        className="select topbar__select"
        value={activeId ?? ""}
        onChange={(e) => setActiveId(e.target.value)}
        disabled={items.length === 0}
      >
        {items.length === 0 && <option value="">{t("dataset.none")}</option>}
        {items.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>
      {active && (
        <span className="topbar__meta" data-testid="snapshot-meta">
          {t("dataset.tx", { count: active.transactions_count })} ·{" "}
          {snap ? t("dataset.snapshot", { id: shortId(snap.id), date: formatDateTime(snap.computed_at) }) : t("dataset.noSnapshot")}
        </span>
      )}
    </div>
  );
}

export function Shell() {
  return (
    <div className="shell">
      <nav className="rail" aria-label={t("nav.primary")}>
        <div className="brand">
          <span className="brand__name">{t("app.name")}</span>
          <span className="brand__team">{t("app.team")}</span>
        </div>
        <NavItems />
        <p className="rail__footer">{t("app.disclaimer")}</p>
      </nav>
      <header className="topbar">
        <DatasetSelect />
        <SimulationBadge />
      </header>
      <nav className="mobile-nav" aria-label={t("nav.primary")}>
        <NavItems />
      </nav>
      <main className="main" id="main">
        <Outlet />
      </main>
    </div>
  );
}
