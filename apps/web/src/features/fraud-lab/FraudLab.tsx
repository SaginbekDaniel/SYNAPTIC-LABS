import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useCan } from "../../app/auth";
import { useDataset } from "../../app/dataset";
import { BandBadge, Disclosure, Empty, ErrorState, Icon, Loading, PageHeader, Panel } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { precisionLabel, t, tDynamic, type MessageKey } from "../../lib/i18n";
import type { AlertPage, AlertSummary, ImportResult, Job, LabSuite } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { alertTitle, alertWhy } from "../alerts/alertText";

const POLL_MS = 1000;
type StepState = "done" | "current" | "todo";

function Stepper({ steps }: { steps: { key: MessageKey; state: StepState }[] }) {
  return (
    <ol className="stepper" aria-label={t("lab.steps")}>
      {steps.map((s, i) => (
        <li key={s.key} className="stepper__step" data-state={s.state} aria-current={s.state === "current" ? "step" : undefined}>
          <span className="stepper__n" aria-hidden="true">
            {s.state === "done" ? <Icon name="check" size={14} /> : i + 1}
          </span>
          <span className="stepper__label">
            {t(s.key)}
            <span className="visually-hidden">{s.state === "done" ? ` — ${t("lab.stepDone")}` : s.state === "current" ? ` — ${t("lab.stepCurrent")}` : ""}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

const JOB_ORDER = ["queued", "running", "succeeded"];

export function FraudLab() {
  const { setActiveId, refresh, list } = useDataset();
  const suites = useApi("lab-suites", (s) => api.get<LabSuite[]>("/api/v1/lab/suites", undefined, s));
  const [suite, setSuite] = useState("demo-v1");
  const [seed, setSeed] = useState("2026");
  const [precision, setPrecision] = useState<"day" | "timestamp">("day");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [top, setTop] = useState<{ total: number; items: AlertSummary[] } | null>(null);
  const [busy, setBusy] = useState<"generate" | "analyse" | null>(null);
  const canAct = useCan("analyst");
  const [error, setError] = useState<ApiError | null>(null);

  const seedNum = Number.parseInt(seed, 10);
  const seedValid = /^\d{1,9}$/.test(seed) && Number.isSafeInteger(seedNum);

  async function generate() {
    setBusy("generate");
    setError(null);
    setJob(null);
    setTop(null);
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
      .get<AlertPage>("/api/v1/alerts", { dataset_id: job.dataset_id, limit: 3 })
      .then((p) => setTop({ total: p.total, items: p.items }))
      .catch((e: ApiError) => setError(e));
  }, [job?.status, job?.dataset_id, refresh]);

  const selectedSuite = suites.data?.find((s) => s.id === suite);
  const stepState = (done: boolean, current: boolean): StepState => (done ? "done" : current ? "current" : "todo");
  const steps = [
    { key: "lab.step.scenario" as const, state: stepState(result !== null, result === null) },
    { key: "lab.step.generate" as const, state: stepState(result !== null, false) },
    { key: "lab.step.analyse" as const, state: stepState(job?.status === "succeeded", result !== null && job?.status !== "succeeded") },
    { key: "lab.step.inspect" as const, state: stepState(false, top !== null) },
  ];

  return (
    <div className="page">
      <PageHeader title={t("lab.title")} description={t("lab.subtitle")} />
      <Stepper steps={steps} />
      <div className="lab-grid">
        <Panel title={t("lab.chooseTitle")} hint={t("lab.chooseHint")} id="lab-config">
          {suites.loading && <Loading rows={3} />}
          {suites.error && <ErrorState error={suites.error} onRetry={suites.reload} />}
          {suites.data && (
            <form
              className="lab-form"
              onSubmit={(e) => {
                e.preventDefault();
                if (canAct && seedValid && !busy) void generate();
              }}
            >
              <fieldset className="suite-grid">
                <legend className="visually-hidden">{t("lab.suite")}</legend>
                {suites.data.map((s) => (
                  <label key={s.id} className="suite-card">
                    <input type="radio" name="suite" value={s.id} checked={suite === s.id} onChange={() => setSuite(s.id)} />
                    <span className="suite-card__body">
                      <span className="suite-card__title">{tDynamic("lab.suiteName.", s.id, s.id)}</span>
                      <span className="suite-card__desc">{tDynamic("lab.suiteDesc.", s.id, s.description)}</span>
                      <span className="suite-card__meta">
                        {t("lab.familiesCount", { count: s.scenario_families.length })} · <code className="mono">{s.id}</code>
                      </span>
                    </span>
                  </label>
                ))}
              </fieldset>
              {selectedSuite && (
                <Disclosure summary={t("lab.familiesOf", { count: selectedSuite.scenario_families.length })}>
                  <ul className="family-list">
                    {selectedSuite.scenario_families.map((f) => (
                      <li key={f}>{tDynamic("family.", f)}</li>
                    ))}
                  </ul>
                </Disclosure>
              )}
              <Disclosure summary={t("lab.advanced")}>
                <div className="lab-advanced">
                  <label className="field">
                    {t("lab.seed")}
                    <input
                      className="input"
                      inputMode="numeric"
                      name="seed"
                      value={seed}
                      onChange={(e) => setSeed(e.target.value.trim())}
                      aria-invalid={!seedValid}
                      aria-describedby="seed-help"
                    />
                    <span className="field__help" id="seed-help">
                      {seedValid ? t("lab.seedHelp") : t("lab.seedInvalid")}
                    </span>
                  </label>
                  <label className="field">
                    {t("lab.precision")}
                    <select className="select" value={precision} onChange={(e) => setPrecision(e.target.value as "day" | "timestamp")}>
                      <option value="day">{t("common.precisionDay")}</option>
                      <option value="timestamp">{t("common.precisionTimestamp")}</option>
                    </select>
                  </label>
                </div>
              </Disclosure>
              {!canAct && (
                <div className="callout" role="note" data-testid="lab-read-only">
                  <Icon name="info" size={16} />
                  {t("role.readOnlyLab")}
                </div>
              )}
              {canAct && (
                <div className="lab-actions">
                  <button type="submit" className="btn btn--primary" disabled={!seedValid || busy !== null}>
                    <Icon name="database" size={16} />
                    {busy === "generate" ? t("lab.generating") : t("lab.generate")}
                  </button>
                  <button type="button" className="btn" onClick={() => void analyse()} disabled={!result || busy !== null || job?.status === "succeeded"}>
                    <Icon name="play" size={16} />
                    {busy === "analyse" ? t("lab.analysing") : t("lab.analyse")}
                  </button>
                </div>
              )}
            </form>
          )}
        </Panel>

        <Panel title={t("lab.resultTitle")} id="lab-steps" className="lab-result">
          <div className="lab-result__body">
            {error && <ErrorState error={error} />}
            {!result && !error && (
              <Empty title={t("lab.resultEmpty")} icon="lab">
                <p>{canAct ? t("lab.resultEmptyHint") : t("lab.resultEmptyReadOnly")}</p>
              </Empty>
            )}
            {result && (
              <section className="lab-block">
                <h3 className="ctx__label">{t("lab.report")}</h3>
                <dl className="figures" data-testid="import-report">
                  <div>
                    <dt>{t("lab.accepted")}</dt>
                    <dd className="num">{result.report.accepted}</dd>
                  </div>
                  <div>
                    <dt>{t("lab.duplicates")}</dt>
                    <dd className="num">{result.report.duplicated_identical}</dd>
                  </div>
                  <div>
                    <dt>{t("lab.quarantined")}</dt>
                    <dd className="num">{result.report.quarantined}</dd>
                  </div>
                  <div>
                    <dt>{t("lab.warnings")}</dt>
                    <dd className="num">{result.report.warning_count}</dd>
                  </div>
                </dl>
              </section>
            )}
            {job && (
              <section className="lab-block" role="status" aria-live="polite">
                <h3 className="ctx__label">{t("lab.job")}</h3>
                <ol className="job-track">
                  {JOB_ORDER.map((s) => {
                    const idx = JOB_ORDER.indexOf(job.status);
                    const me = JOB_ORDER.indexOf(s);
                    const state = job.status === "failed" || job.status === "cancelled" ? "todo" : me < idx || job.status === "succeeded" ? "done" : me === idx ? "current" : "todo";
                    return (
                      <li key={s} data-state={state}>
                        <span className="job-track__dot" aria-hidden="true" />
                        {tDynamic("job.", s)}
                      </li>
                    );
                  })}
                </ol>
                <span data-testid="job-status" className="job-status">
                  {t("lab.jobStatus", { status: tDynamic("job.", job.status) })}
                </span>
                {job.status === "queued" && <span className="ctx__note">{t("lab.jobWaiting")}</span>}
                {job.status === "failed" && <div className="callout callout--error">{t("lab.jobFailed", { code: job.error_code ?? "—" })}</div>}
              </section>
            )}
            {top && (
              <section className="lab-block">
                <h3 className="ctx__label">{t("lab.detected", { count: top.total })}</h3>
                {top.items.length === 0 ? (
                  <p className="ctx__note">{t("lab.noneDetected")}</p>
                ) : (
                  <ul className="lab-alerts">
                    {top.items.map((a) => (
                      <li key={a.id}>
                        <Link to={`/alerts/${a.id}`} className="lab-alert">
                          <span className="lab-alert__main">
                            <strong>{alertTitle(a)}</strong>
                            <span className="ctx__note">{alertWhy(a)}</span>
                          </span>
                          <BandBadge band={a.risk.band} size="sm" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
                <Link className="btn btn--primary" to="/alerts" data-testid="to-alerts">
                  {t("lab.toAlerts", { count: top.total })}
                  <Icon name="arrowRight" size={16} />
                </Link>
              </section>
            )}
          </div>
        </Panel>
      </div>

      <Panel title={t("lab.datasets")} hint={t("lab.datasetsHint")} flush>
        {list.data && list.data.items.length === 0 && <Empty title={t("dataset.none")} icon="database" />}
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
        <caption className="visually-hidden">{t("lab.datasets")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("dataset.label")}</th>
            <th scope="col" className="right">
              {t("command.transactions")}
            </th>
            <th scope="col">{t("common.precision")}</th>
            <th scope="col">{t("lab.analysis")}</th>
            <th scope="col">
              <span className="visually-hidden">{t("common.actions")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {list.data!.items.map((d) => (
            <tr key={d.id}>
              <td>
                {d.name}
                <div className="cell-note">{formatDateTime(d.created_at)}</div>
              </td>
              <td className="right num">{d.transactions_count}</td>
              <td>{precisionLabel(d.time_precision)}</td>
              <td>{d.latest_job ? tDynamic("job.", d.latest_job.status) : t("dataset.noSnapshot")}</td>
              <td className="right">
                {d.id === activeId ? (
                  <span className="badge badge--accent">{t("lab.active")}</span>
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
