import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { PageHeader, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { t, tDynamic } from "../../lib/i18n";
import { TRANSFER_ROUTE, toMinorUnits } from "./contract";

type Intent = components["schemas"]["SandboxIntentRequest"];
type Assessment = components["schemas"]["SandboxAssessmentResponse"];
type Evidence = components["schemas"]["SandboxEvidenceResponse"];
type Action = components["schemas"]["SandboxActionRequest"]["action"];
type Acknowledgement = components["schemas"]["SandboxAcknowledgement"];

const API = "/api/v1/sandbox/transfers";
const ROUTE = `${TRANSFER_ROUTE}/sandbox`;
const actions: Partial<Record<Assessment["status"], Action[]>> = {
  READY: ["CONFIRM", "CANCEL"],
  AWAITING_CONFIRMATION: ["CONFIRM", "HOLD_FOR_REVIEW", "CANCEL"],
  STEP_UP_REQUIRED: ["VERIFY_STEP_UP", "HOLD_FOR_REVIEW", "CANCEL"],
  IN_REVIEW: ["APPROVE_REVIEW", "CANCEL"],
  UNAVAILABLE: ["CANCEL"],
};

export function SandboxTransfer() {
  const { assessmentId } = useParams();
  const navigate = useNavigate();
  const token = useRef<HTMLInputElement>(null);
  const draft = useRef<Intent | null>(null);
  const actionKeys = useRef(new Map<string, string>());
  const [result, setResult] = useState<Assessment | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [ack, setAck] = useState<Acknowledgement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [beneficiary, setBeneficiary] = useState("demo-replay");
  const [amount, setAmount] = useState("98000");
  const [requested, setRequested] = useState("2026-10-23T12:00:00Z");
  const visible = result?.assessment_id === assessmentId ? result : null;

  function headers() {
    return { Authorization: `Bearer ${token.current?.value.trim() ?? ""}` };
  }

  async function run(work: () => Promise<void>) {
    if (busy) return;
    if (!token.current?.value.trim()) {
      setError(t("sandbox.tokenRequired"));
      token.current?.focus();
      return;
    }
    setBusy(true);
    setError("");
    try {
      await work();
    } catch {
      setError(t("sandbox.error"));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const minor = toMinorUnits(amount);
    if (minor === null) {
      setError(t("transfer.amountInvalid"));
      return;
    }
    const retry = visible?.status === "UNAVAILABLE" ? visible.assessment_id : undefined;
    const previousDraft = draft.current?.supersedes_assessment_id === retry ? draft.current : null;
    const intent: Intent = previousDraft ?? {
      intent_id: crypto.randomUUID(),
      beneficiary: beneficiary.trim(),
      amount_minor: minor,
      requested_at: requested.trim(),
      currency: "KZT",
      channel: "web",
      supersedes_assessment_id: retry,
    };
    draft.current = intent;
    void run(async () => {
      const response = await api.post<Assessment>(API, intent, { headers: headers(), signal: AbortSignal.timeout(5000) });
      setResult(response);
      setEvidence(null);
      setAck(null);
      navigate(`${ROUTE}/${response.assessment_id}`, { replace: true });
    });
  }

  function reload(withEvidence: boolean) {
    if (!assessmentId) return;
    const path = `${API}/${assessmentId}`;
    void run(async () => {
      if (withEvidence) {
        const response = await api.get<Evidence>(`${path}/evidence`, undefined, AbortSignal.timeout(5000), headers());
        setEvidence(response);
        setResult(response.assessment);
      } else {
        setResult(await api.get<Assessment>(path, undefined, AbortSignal.timeout(5000), headers()));
        setEvidence(null);
      }
    });
  }

  function apply(action: Action) {
    if (!visible) return;
    const key = `${visible.assessment_id}:${action}`;
    const id = actionKeys.current.get(key) ?? crypto.randomUUID();
    actionKeys.current.set(key, id);
    void run(async () => {
      const response = await api.post<Acknowledgement>(`${API}/${visible.assessment_id}/actions`,
        { action_id: id, action }, { headers: headers(), signal: AbortSignal.timeout(5000) });
      setAck(response);
      setResult({ ...visible, status: response.to_status });
    });
  }

  return (
    <div className="page">
      <PageHeader title={t("sandbox.title")} description={t("sandbox.description")}
        actions={<Link className="btn" to={TRANSFER_ROUTE}>{t("sandbox.back")}</Link>} />
      <Panel title={t("sandbox.access")}>
        <div className="lab-form">
          <label className="field">
            {t("sandbox.token")}
            <input ref={token} className="input" type="password" autoComplete="off" disabled={busy}
              onChange={() => { setEvidence(null); setResult(null); setAck(null); }} />
          </label>
          {assessmentId && <div className="lab-actions">
            <button className="btn" onClick={() => reload(false)} disabled={busy}>{t("sandbox.restore")}</button>
            <button className="btn" onClick={() => reload(true)} disabled={busy}>{t("sandbox.evidence")}</button>
            <Link className="btn" to={ROUTE} onClick={() => { draft.current = null; setResult(null); setEvidence(null); }}>
              {t("sandbox.new")}
            </Link>
          </div>}
        </div>
      </Panel>
      {(!assessmentId || visible?.status === "UNAVAILABLE") &&
        <Panel title={t("transfer.formTitle")}>
          <form className="lab-form" aria-busy={busy} onSubmit={submit}>
            <label className="field">{t("sandbox.beneficiary")}
              <input className="input" required value={beneficiary} onChange={(event) => {
                draft.current = null;
                setBeneficiary(event.target.value);
              }} />
            </label>
            <label className="field">{t("transfer.amount", { currency: "KZT" })}
              <input className="input" required inputMode="decimal" value={amount} onChange={(event) => {
                draft.current = null;
                setAmount(event.target.value);
              }} />
            </label>
            <label className="field">{t("sandbox.cutoff")}
              <input className="input" required value={requested} onChange={(event) => {
                draft.current = null;
                setRequested(event.target.value);
              }} />
            </label>
            <button className="btn btn--primary" type="submit" disabled={busy}>
              {t(visible ? "sandbox.retry" : "transfer.check")}
            </button>
          </form>
        </Panel>}
      {error && <p role="alert" className="transfer-error">{error}</p>}
      {visible && <Panel title={t("transfer.result")}>
        <div aria-live="polite" data-testid="sandbox-result" data-status={visible.status}>
          <p><strong>{t(`transfer.decision.${visible.decision}`)}</strong></p>
          <p>{visible.customer_message}</p>
          <p data-testid="transfer-risk-band" data-band={visible.risk_band}>
            {t("transfer.riskBand", { band: t(`transfer.risk.${visible.risk_band}`) })}
          </p>
          <p>{tDynamic("sandbox.status.", visible.status)} · {visible.policy_version}</p>
          {ack && <p>{t("sandbox.ack", { action: tDynamic("sandbox.action.", ack.action) })}</p>}
        </div>
        <div className="lab-actions">
          {(actions[visible.status] ?? []).map((action) =>
            <button className="btn" key={action} type="button" onClick={() => apply(action)} disabled={busy}>
              {tDynamic("sandbox.action.", action)}
            </button>)}
        </div>
      </Panel>}
      {evidence?.profile && <Panel title={t("sandbox.evidence")}>
        <p>{t("sandbox.snapshot", { id: evidence.profile.snapshot_id, date: evidence.profile.as_of })}</p>
        <p>{t("sandbox.transactions", { count: evidence.profile.transactions.length })}</p>
        <ul className="family-list">
          {evidence.profile.context.map((fact) => <li key={fact.source_ref}>{fact.kind} · {fact.known_at}</li>)}
        </ul>
      </Panel>}
    </div>
  );
}
