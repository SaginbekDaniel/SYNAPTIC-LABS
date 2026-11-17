import { useNavigate } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { BandBadge, CaseStatusBadge, Empty, ErrorState, Loading, NoDataset, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { t, tDynamic } from "../../lib/i18n";
import type { CasePage } from "../../lib/types";
import { useApi } from "../../lib/useApi";

export function CasesList() {
  const { activeId } = useDataset();
  const navigate = useNavigate();
  const cases = useApi(activeId ? `cases:${activeId}` : null, (s) => api.get<CasePage>("/api/v1/cases", { dataset_id: activeId, limit: 200 }, s));
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t("case.listTitle")}</h1>
          <p>{t("case.listSubtitle")}</p>
        </div>
      </div>
      <Panel flush>
        {!activeId && <NoDataset />}
        {cases.loading && !cases.data && (
          <div className="panel__body">
            <Loading />
          </div>
        )}
        {cases.error && <ErrorState error={cases.error} onRetry={cases.reload} />}
        {cases.data && cases.data.items.length === 0 && <Empty title={t("case.empty")} />}
        {cases.data && cases.data.items.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <caption className="visually-hidden">{t("case.listTitle")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("case.title")}</th>
                  <th scope="col">{t("common.status")}</th>
                  <th scope="col">{t("alert.priority")}</th>
                  <th scope="col">{t("case.decision")}</th>
                  <th scope="col">{t("case.opened")}</th>
                </tr>
              </thead>
              <tbody>
                {cases.data.items.map((c) => (
                  <tr key={c.id} className="is-clickable" onClick={() => navigate(`/alerts/${c.alert_id}`)}>
                    <td>
                      <a
                        href={`/alerts/${c.alert_id}`}
                        onClick={(e) => {
                          e.preventDefault();
                          navigate(`/alerts/${c.alert_id}`);
                        }}
                      >
                        <code className="mono">{c.title}</code>
                      </a>
                    </td>
                    <td>
                      <CaseStatusBadge status={c.status} />
                    </td>
                    <td>
                      <BandBadge band={c.band} />
                    </td>
                    <td>{c.decision ? tDynamic("cs.", c.decision) : "—"}</td>
                    <td className="num">{formatDateTime(c.opened_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
