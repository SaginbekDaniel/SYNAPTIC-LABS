import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { Empty, ErrorState, Loading, Panel } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { precisionLabel, t, tDynamic } from "../../lib/i18n";
import type { AlertPage, ImportResult, Job, LabSuite } from "../../lib/types";
import { useApi } from "../../lib/useApi";

const POLL_MS = 1000;

export function FraudLab() {
  const { setActiveId, refresh, list } = useDataset();
  const suites = useApi("lab-suites", (s) => api.get<LabSuite[]>("/api/v1/lab/suites", undefined, s));
  const [suite, setSuite] = useState("demo-v1");
  const [seed, setSeed] = useState("2026");
  const [precision, setPrecision] = useState<"day" | "timestamp">("day");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [alertCount, setAlertCount] = useState<number | null>(null);
  const [busy, setBusy] = useState<"generate" | "analyse" | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const seedNum = Number.parseInt(seed, 10);
  const seedValid = /^\d{1,9}$/.test(seed) && Number.isSafeInteger(seedNum);

  async function generate() {
    setBusy("generate");
    setError(null);
    setJob(null);
    setAlertCount(null);
    try {
      const r = await api.post<ImportResult>("/api/v1/lab/datasets", { suite, seed: seedNum, precision });
      setResult(r);
      setActiveId(r.dataset.id);
      refresh();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(null);
    }
  }

  async function analyse() {
    if (!result) return;
    setBusy("analyse");
    setError(null);
    try {
      setJob(await api.post<Job>("/api/v1/analysis/jobs", { dataset_id: result.dataset.id }));
    } catch (e) {
      setError(e as ApiError);
      setBusy(null);
    }
  }

  // Poll the persisted job state; the UI never simulates progress on its own.
  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") {
      if (job && busy === "analyse") setBusy(null);
      return;
    }
    const handle = window.setTimeout(async () => {
      try {
        setJob(await api.get<Job>(`/api/v1/analysis/jobs/${job.id}`));
      } catch (e) {
        setError(e as ApiError);
        setBusy(null);
      }
    }, POLL_MS);
    return () => window.clearTimeout(handle);
  }, [job, busy]);

  useEffect(() => {
    if (job?.status !== "succeeded") return;
    refresh();
    api
      .get<AlertPage>("/api/v1/alerts", { dataset_id: job.dataset_id, limit: 1 })
      .then((p) => setAlertCount(p.total))
      .catch((e: ApiError) => setError(e));
  }, [job?.status, job?.dataset_id, refresh]);

  const selectedSuite = suites.data?.find((s) => s.id === suite);
  const steps = [
    { key: "lab.step1" as const, done: result !== null },
    { key: "lab.step2" as const, done: job !== null },
    { key: "lab.step3" as const, done: job?.status === "succeeded" },
    { key: "lab.step4" as const, done: alertCount !== null },
  ];

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t("lab.title")}</h1>
          <p>{t("lab.subtitle")}</p>
        </div>
      </div>
      <div className="grid-2">
        <Panel title={t("lab.suite")} id="lab-config">
          {suites.loading && <Loading rows={3} />}
          {suites.error && <ErrorState error={suites.error} onRetry={suites.reload} />}
          {suites.data && (
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                if (seedValid && !busy) void generate();
              }}
            >
              <div className="row" style={{ alignItems: "flex-end" }}>
                <label className="field" style={{ flex: "2 1 180px" }}>
                  {t("lab.suite")}
                  <select className="select" value={suite} onChange={(e) => setSuite(e.target.value)} name="suite">
                    {suites.data.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field" style={{ flex: "1 1 90px" }}>
                  {t("lab.seed")}
                  <input
                    className="input"
                    inputMode="numeric"
                    name="seed"
                    value={seed}
                    onChange={(e) => setSeed(e.target.value.trim())}
                    aria-invalid={!seedValid}
                  />
                </label>
                <label className="field" style={{ flex: "1 1 130px" }}>
                  {t("lab.precision")}
                  <select className="select" value={precision} onChange={(e) => setPrecision(e.target.value as "day" | "timestamp")}>
                    <option value="day">{t("common.precisionDay")}</option>
                    <option value="timestamp">{t("common.precisionTimestamp")}</option>
                  </select>
                </label>
              </div>
              {selectedSuite && (
                <div className="stack stack--sm">
                  <span className="subtle">{selectedSuite.description}</span>
                  <h3>{t("lab.families")}</h3>
                  <ul className="subtle" style={{ margin: 0, paddingLeft: "1.1rem" }}>
                    {selectedSuite.scenario_families.map((f) => (
                      <li key={f}>{tDynamic("family.", f)}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="row">
                <button type="submit" className="btn btn--primary" disabled={!seedValid || busy !== null}>
                  {busy === "generate" ? t("lab.generating") : t("lab.generate")}
                </button>
                <button type="button" className="btn" onClick={() => void analyse()} disabled={!result || busy !== null || job?.status === "succeeded"}>
                  {busy === "analyse" ? t("lab.analysing") : t("lab.analyse")}
                </button>
              </div>
            </form>
          )}
        </Panel>

        <Panel title={t("lab.steps")} id="lab-steps">
          <div className="stack">
            <ol className="steps">
              {steps.map((s, i) => (
                <li key={s.key} className="step" data-done={s.done ? "true" : "false"}>
                  <span className="step__n" aria-hidden="true">
                    {i + 1}
                  </span>
                  <span>
                    {t(s.key)}
                    <span className="visually-hidden">{s.done ? ` — ${t("common.yes")}` : ""}</span>
                  </span>
                </li>
              ))}
            </ol>
            {error && <ErrorState error={error} />}
            {result && (
              <dl className="kv" data-testid="import-report">
                <dt>{t("lab.accepted")}</dt>
                <dd className="num">{result.report.accepted}</dd>
                <dt>{t("lab.duplicates")}</dt>
                <dd className="num">{result.report.duplicated_identical}</dd>
                <dt>{t("lab.quarantined")}</dt>
                <dd className="num">{result.report.quarantined}</dd>
                <dt>{t("lab.warnings")}</dt>
                <dd className="num">{result.report.warning_count}</dd>
              </dl>
            )}
            {job && (
              <div role="status" aria-live="polite" className="stack stack--sm">
                <span data-testid="job-status">{t("lab.jobStatus", { status: tDynamic("job.", job.status) })}</span>
                {job.status === "queued" && <span className="subtle">{t("lab.jobWaiting")}</span>}
                {job.status === "failed" && <div className="callout callout--error">{t("lab.jobFailed", { code: job.error_code ?? "—" })}</div>}
              </div>
            )}
            {alertCount !== null && (
              <Link className="btn btn--primary" to="/alerts" data-testid="to-alerts">
                {t("lab.toAlerts", { count: alertCount })}
              </Link>
            )}
          </div>
        </Panel>
      </div>
      <Panel title={t("lab.datasets")} flush>
        {list.data && list.data.items.length === 0 && <Empty title={t("dataset.none")} />}
        {list.data && list.data.items.length > 0 && <DatasetTable />}
        {list.loading && !list.data && (
          <div className="panel__body">
            <Loading rows={2} />
          </div>
        )}
      </Panel>
    </div>
  );
}

function DatasetTable() {
  const { list, activeId, setActiveId } = useDataset();
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">{t("dataset.label")}</th>
            <th scope="col" className="right">
              {t("command.transactions")}
            </th>
            <th scope="col">{t("common.precision")}</th>
            <th scope="col">{t("command.snapshot")}</th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          {list.data!.items.map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td className="right num">{d.transactions_count}</td>
              <td>{precisionLabel(d.time_precision)}</td>
              <td>{d.latest_job ? tDynamic("job.", d.latest_job.status) : t("dataset.noSnapshot")}</td>
              <td className="right">
                {d.id === activeId ? (
                  <span className="badge">{t("lab.active")}</span>
                ) : (
                  <button type="button" className="btn btn--sm" onClick={() => setActiveId(d.id)}>
                    {t("lab.use")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
