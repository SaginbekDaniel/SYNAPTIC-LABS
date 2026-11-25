import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ErrorState, Icon, Loading, PageHeader, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { t, tDynamic } from "../../lib/i18n";
import { useApi } from "../../lib/useApi";
import { TRANSFER_API, TRANSFER_ROUTE, toMinorUnits, toTenge } from "./contract";
import type { AssessmentLink, CheckRequest, CheckResult, ScenarioOption } from "./contract";

type Action = CheckResult["recommended_actions"][number];
type Completion = "CONTINUE_SIMULATION" | "CANCEL";

export function TransferProtection() {
  const options = useApi("transfer-scenarios", (signal) => api.get<ScenarioOption[]>(`${TRANSFER_API}/scenarios`, undefined, signal));
  const [scenarioId, setScenarioId] = useState("");
  const scenario = options.data?.find((item) => item.scenario_id === scenarioId) ?? options.data?.[0];
  return (
    <div className="page">
      <PageHeader title={t("transfer.title")} description={t("transfer.subtitle")}
        actions={<Link className="btn" to={`${TRANSFER_ROUTE}/sandbox`}>{t("sandbox.title")}</Link>} />
      {options.error ? <ErrorState error={options.error} onRetry={options.reload} /> : null}
      {options.loading ? <Loading /> : null}
      {scenario && options.data ? (
        <TransferForm key={scenario.scenario_id} scenario={scenario} options={options.data} selectScenario={setScenarioId} />
      ) : null}
    </div>
  );
}

function TransferForm({ scenario, options, selectScenario }: {
  scenario: ScenarioOption;
  options: ScenarioOption[];
  selectScenario: (id: string) => void;
}) {
  const [amount, setAmount] = useState(toTenge(scenario.amount_minor));
  const [pending, setPending] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const [result, setResult] = useState<{ check: CheckRequest; response: CheckResult } | null>(null);
  const [failure, setFailure] = useState<"TIMEOUT" | "DEPENDENCY_FAILURE" | null>(null);
  const [completion, setCompletion] = useState<Completion | null>(null);
  const [support, setSupport] = useState(false);
  const requestInProgress = useRef(false);
  const details = useRef<HTMLHeadingElement>(null);

  async function check() {
    if (requestInProgress.current || completion) return;
    const minor = toMinorUnits(amount);
    setInvalid(minor === null);
    if (minor === null) return;
    const payload: CheckRequest = {
      scenario_id: scenario.scenario_id,
      recipient_id: scenario.recipient_id,
      currency: scenario.currency,
      amount_minor: minor,
      client_context: "none",
    };
    requestInProgress.current = true;
    setPending(true);
    setResult(null);
    setFailure(null);
    setSupport(false);
    try {
      const response = await api.post<CheckResult>(TRANSFER_API, payload, { signal: AbortSignal.timeout(5000) });
      setResult({ check: payload, response });
    } catch (error) {
      setFailure(error instanceof DOMException && error.name === "TimeoutError" ? "TIMEOUT" : "DEPENDENCY_FAILURE");
    } finally {
      requestInProgress.current = false;
      setPending(false);
    }
  }

  function followAction(action: Action) {
    if (completion) return;
    if (action === "RETRY") void check();
    if (action === "REVIEW_DETAILS") details.current?.focus();
    if (action === "CONTACT_OFFICIAL_SUPPORT") setSupport(true);
    if (action === "CANCEL" || action === "CONTINUE_SIMULATION") setCompletion(action);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void check();
  }

  const purpose = tDynamic("transfer.purpose.", scenario.scenario_id, "");
  const response = result?.response;
  const decision = response?.decision ?? (failure ? "UNAVAILABLE" : undefined);
  const link: AssessmentLink | undefined = result?.response.snapshot_id
    ? { check: result.check, assessment_id: result.response.assessment_id }
    : undefined;

  return (
    <div className="lab-grid">
      <Panel title={t("transfer.formTitle")} id="transfer-form">
        <form className="lab-form" onSubmit={submit} aria-busy={pending} noValidate>
          <label className="field">
            {t("transfer.scenario")}
            <select className="select" value={scenario.scenario_id} disabled={pending} onChange={(event) => selectScenario(event.target.value)}>
              {options.map((item) => (
                <option key={item.scenario_id} value={item.scenario_id}>{tDynamic("transfer.scenario.", item.scenario_id)}</option>
              ))}
            </select>
          </label>
          <section className="transfer-details" aria-labelledby="transfer-details-title">
            <h3 id="transfer-details-title" tabIndex={-1} ref={details}>{t("transfer.details")}</h3>
            <dl className="transfer-facts">
              <div><dt>{t("common.from")}</dt><dd>{t("transfer.sender")}</dd></div>
              <div><dt>{t("common.to")}</dt><dd>{tDynamic("transfer.recipient.", scenario.recipient_id)}</dd></div>
              {purpose ? <div><dt>{t("transfer.purpose")}</dt><dd>{purpose}</dd></div> : null}
            </dl>
          </section>
          <label className="field">
            {t("transfer.amount", { currency: scenario.currency })}
            <input className="input num" type="text" inputMode="decimal" maxLength={39} value={amount}
              aria-invalid={invalid} aria-describedby={invalid ? "transfer-amount-error" : undefined} disabled={pending}
              onChange={(event) => {
                setAmount(event.target.value);
                setInvalid(false);
                setResult(null);
                setFailure(null);
                setCompletion(null);
                setSupport(false);
              }}
            />
          </label>
          {invalid ? <p id="transfer-amount-error" className="transfer-error" role="alert">{t("transfer.amountInvalid")}</p> : null}
          {completion ? (
            <button className="btn" type="button" onClick={() => {
              setCompletion(null); setResult(null); setFailure(null); setSupport(false);
            }}>{t("transfer.restart")}</button>
          ) : (
            <button className="btn btn--primary" type="submit" disabled={pending || !!response}>
              <Icon name="search" size={18} /> {t(pending ? "transfer.checking" : "transfer.check")}
            </button>
          )}
        </form>
      </Panel>
      <Panel title={t("transfer.result")} id="transfer-result">
        <div aria-live="polite" aria-atomic="true">
          {decision ? (
            <div className="transfer-result" data-decision={decision}>
              <strong>{t(`transfer.decision.${decision}`)}</strong>
              <p>{response?.customer_message ?? t(`transfer.message.${decision}`)}</p>
              {response && <p data-testid="transfer-risk-band" data-band={response.risk_band}>
                {t("transfer.riskBand", { band: t(`transfer.risk.${response.risk_band}`) })}
              </p>}
              {response?.reason_codes.length || failure ? (
                <ul className="transfer-reasons">
                  {(response?.reason_codes ?? (failure ? [failure] : [])).map((code) => <li key={code}>{t(`transfer.reason.${code}`)}</li>)}
                </ul>
              ) : null}
            </div>
          ) : <p className="transfer-muted">{t(pending ? "transfer.checking" : "transfer.resultEmpty")}</p>}
          {completion ? <p className="transfer-confirmation">{t(`transfer.completed.${completion}`)}</p> : null}
          {support && !completion ? <p className="transfer-confirmation">{t("transfer.supportHint")}</p> : null}
        </div>
        {decision && !completion ? (
          <div className="transfer-actions">
            {(response?.recommended_actions ?? ["RETRY", "CANCEL"] as const).map((action) => (
              <button className={action === "CONTINUE_SIMULATION" && decision === "ALLOW" ? "btn btn--primary" : "btn"}
                key={action} type="button" disabled={pending} onClick={() => followAction(action)}>
                {t(`transfer.action.${action}`)}
              </button>
            ))}
          </div>
        ) : null}
        {link ? <Link className="transfer-analyst" to={`${TRANSFER_ROUTE}/investigation`} state={link}>{t("transfer.analystLink")}</Link> : null}
      </Panel>
    </div>
  );
}
