import { useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { GraphCanvas, type GraphEdgeSpec, type GraphNodeSpec } from "../../components/graph/GraphCanvas";
import { BandBadge, PageHeader, Panel, TxTable } from "../../components/ui";
import { ApiError, api } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { t, tDynamic } from "../../lib/i18n";
import { EvidenceTimeline } from "../investigation/EvidenceTimeline";
import { TRANSFER_API, TRANSFER_ROUTE } from "./contract";
import type { AssessmentEvidence, AssessmentLink } from "./contract";

export function TransferInvestigation() {
  const { state } = useLocation();
  const link = state as AssessmentLink | null;
  return (
    <div className="page">
      <PageHeader title={t("transfer.investigationTitle")}
        back={{ to: TRANSFER_ROUTE, label: t("transfer.back") }} />
      {link?.check && link.assessment_id ? (
        <AuthorizedAssessment key={link.assessment_id} link={link} />
      ) : (
        <Panel><p>{t("transfer.investigationEmpty")}</p><Link to={TRANSFER_ROUTE}>{t("transfer.back")}</Link></Panel>
      )}
    </div>
  );
}

function AuthorizedAssessment({ link }: { link: AssessmentLink }) {
  const [evidence, setEvidence] = useState<AssessmentEvidence | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "denied" | "stale" | "error">("idle");
  const token = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);

  async function openEvidence(event: FormEvent) {
    event.preventDefault();
    if (!token.current || inFlight.current) return;
    const value = token.current.value.trim();
    token.current.value = "";
    inFlight.current = true;
    setStatus("loading");
    try {
      const details = await api.post<AssessmentEvidence>(`${TRANSFER_API}/evidence`, link, {
        signal: AbortSignal.timeout(5000),
        headers: { "X-Nexora-Transfer-Analyst-Token": value },
      });
      setEvidence(details);
      setStatus("idle");
    } catch (error) {
      setStatus(error instanceof ApiError && (error.status === 401 || error.status === 403) ? "denied"
        : error instanceof ApiError && error.status === 404 ? "stale" : "error");
    } finally {
      inFlight.current = false;
    }
  }

  if (evidence) return <EvidenceDetails evidence={evidence} close={() => setEvidence(null)} />;
  return (
    <Panel title={t("transfer.analystAccess")} id="transfer-analyst-access">
      <form className="lab-form transfer-access" onSubmit={openEvidence} aria-busy={status === "loading"}>
        <label className="field">
          {t("transfer.token")}
          <input className="input" ref={token} required type="password" autoComplete="off" maxLength={256} disabled={status === "loading"} />
        </label>
        <button className="btn btn--primary" type="submit" disabled={status === "loading"}>
          {t(status === "loading" ? "state.loading" : "transfer.openEvidence")}
        </button>
        {status !== "idle" && status !== "loading" ? (
          <p className="transfer-error" role="alert">{t(`transfer.access.${status}`)}</p>
        ) : null}
      </form>
    </Panel>
  );
}

function EvidenceDetails({ evidence, close }: { evidence: AssessmentEvidence; close: () => void }) {
  const transactions = [...evidence.transactions].sort((a, b) => a.observed_date.localeCompare(b.observed_date)
    || (a.occurred_at ?? "").localeCompare(b.occurred_at ?? "") || a.id.localeCompare(b.id));
  const references = new Set(evidence.formations.flatMap((formation) => formation.indicators.flatMap((item) => item.transaction_ids)));
  const nodes = new Map<string, GraphNodeSpec>([[evidence.recipient_account_id, { id: evidence.recipient_account_id, role: "subject" }]]);
  const edges = new Map<string, GraphEdgeSpec>();
  for (const tx of transactions) {
    const from = tx.sender_account_id;
    const to = tx.receiver_account_id;
    if (!nodes.has(from)) nodes.set(from, { id: from, role: "entry" });
    if (!nodes.has(to)) nodes.set(to, { id: to, role: "exit" });
    const id = JSON.stringify([from, to, tx.currency]);
    const previous = edges.get(id);
    edges.set(id, {
      id, source: from, target: to, currency: tx.currency,
      amountMinor: (BigInt(previous?.amountMinor ?? "0") + BigInt(tx.amount_minor)).toString(),
      count: (previous?.count ?? 0) + 1,
      highlighted: previous?.highlighted || references.has(tx.id),
    });
  }

  return (
    <>
      <div className="lab-grid">
        <Panel title={t("transfer.snapshot")} id="transfer-snapshot"
          actions={<button className="btn btn--sm" type="button" onClick={close}>{t("common.close")}</button>}>
          <dl className="transfer-facts transfer-audit">
            <div><dt>{t("transfer.assessmentId")}</dt><dd className="num">{evidence.assessment_id}</dd></div>
            <div><dt>{t("transfer.snapshotId")}</dt><dd className="num">{evidence.snapshot_id}</dd></div>
            <div><dt>{t("transfer.graphSnapshot")}</dt><dd className="num">{evidence.graph_snapshot_id}</dd></div>
            <div><dt>{t("transfer.asOf")}</dt><dd>{formatDateTime(evidence.as_of)}</dd></div>
            <div><dt>{t("transfer.graphAsOf")}</dt><dd>{formatDateTime(evidence.graph_as_of)}</dd></div>
            <div><dt>{t("transfer.validUntil")}</dt><dd>{formatDateTime(evidence.valid_until)}</dd></div>
            <div><dt>{t("transfer.policy")}</dt><dd>{evidence.policy_version}</dd></div>
            <div><dt>{t("transfer.graphPolicy")}</dt><dd>{evidence.graph_policy_version}</dd></div>
          </dl>
        </Panel>
        <Panel title={t("transfer.findings")} id="transfer-findings" className="transfer-findings">
          <ul className="transfer-reasons">
            {evidence.reason_codes.map((reason) => <li key={reason}>{t(`transfer.reason.${reason}`)}</li>)}
            {evidence.is_repeat_recipient && !evidence.reason_codes.includes("ESTABLISHED_RELATIONSHIP")
              ? <li>{t("transfer.reason.ESTABLISHED_RELATIONSHIP")}</li> : null}
          </ul>
          {evidence.formations.map((formation) => (
            <div className="transfer-finding" key={formation.formation_id}>
              <h3>{tDynamic("kind.", formation.kind)} <BandBadge band={formation.band} size="sm" /></h3>
              <ul className="transfer-reasons">
                {formation.indicators.map((indicator) => (
                  <li key={indicator.evidence_id}>
                    {tDynamic("transfer.signal.", indicator.status)} <code>{indicator.reason_code}</code>
                    {" · "}{t("transfer.refCount", { count: indicator.transaction_ids.length })}
                  </li>
                ))}
              </ul>
              <p className="transfer-muted">{formation.limitations.map((limit) => tDynamic("lim.", limit)).join(" · ")}</p>
            </div>
          ))}
          {evidence.context.map((fact) => (
            <div className="transfer-finding" key={fact.source_ref}>
              <strong>{tDynamic("transfer.context.", fact.kind)}</strong>
              <p className="transfer-muted">{t("transfer.knownAt", { date: formatDateTime(fact.known_at) })}</p>
              <code>{fact.source_ref}</code>
            </div>
          ))}
        </Panel>
      </div>
      {transactions.length > 0 ? (
        <>
          <Panel title={t("transfer.graph")} id="transfer-graph">
            <GraphCanvas nodes={[...nodes.values()]} edges={[...edges.values()]}
              highlightEdges={new Set([...edges.values()].filter((edge) => edge.highlighted).map((edge) => edge.id))} />
          </Panel>
          <Panel title={t("transfer.timeline")} id="transfer-timeline">
            <EvidenceTimeline txs={transactions} center={evidence.recipient_account_id} highlight={references}
              windowStart={transactions[0]!.observed_date} windowEnd={transactions[transactions.length - 1]!.observed_date} />
            <TxTable rows={transactions} highlight={references} caption={t("transfer.references")} />
            <details className="transfer-provenance">
              <summary>{t("transfer.knownTimes")}</summary>
              <ul className="transfer-reasons">
                {transactions.map((tx) => <li key={tx.id}><code>{tx.source_transaction_id}</code> · {formatDateTime(tx.ingested_at)}</li>)}
              </ul>
            </details>
          </Panel>
        </>
      ) : null}
    </>
  );
}
