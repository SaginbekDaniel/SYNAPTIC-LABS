import { NavLink } from "react-router-dom";
import { t } from "../../lib/i18n";

/** Analytics sub-views: operational dataset analytics and the offline benchmark. */
export function AnalyticsTabs() {
  return (
    <nav className="tabs" aria-label={t("analytics.views")}>
      <NavLink to="/analytics" end className="tabs__item">
        {t("analytics.tab.dataset")}
      </NavLink>
      <NavLink to="/analytics/benchmark" className="tabs__item">
        {t("analytics.tab.benchmark")}
      </NavLink>
    </nav>
  );
}
