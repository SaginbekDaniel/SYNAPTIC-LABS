import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { GraphCanvas, GraphLegend } from "../../components/graph/GraphCanvas";
import { AccountId, BandBadge, ErrorState, EvidenceBadge, Loading, Money, Panel, TxTable } from "../../components/ui";
import { api } from "../../lib/api";
import { formatBp, formatDate, shortId } from "../../lib/format";
import { kindLabel, precisionLabel, reasonPolarity, reasonText, t, tDynamic } from "../../lib/i18n";
import type { AlertDetail, EvidenceChain, EvidenceItem, ReasonCode } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { CasePanel } from "./CasePanel";
import { buildFormationGraph } from "./formationGraph";

function evidenceForReason(code: string, evidence: EvidenceItem[]): EvidenceItem | undefined {
  if (code.startsWith("STRUCT_")) return evidence.find((e) => e.kind === "graph_fact");
  // Match by reason code: context counter-evidence also has kind "counterevidence".
  if (code.startsWith("TEMPORAL_")) return evidence.find((e) => e.reason_code.startsWith("TEMPORAL_"));
  if (code === "BENIGN_CONTEXT") return evidence.find((e) => e.reason_code.startsWith("CTX_"));
  return undefined;
}

function Hypothesis({ alert }: { alert: AlertDetail }) {
  const f = alert.formation;
  if (f.kind === "funnel") {
    const downstream = f.exit_ids.length
      ? t("alert.hypothesis.funnelDown", { count: f.exit_ids.length })
      : t("alert.hypothesis.funnelNoDown");
    return (
      <p>
        {t("alert.hypothesis.funnel", { feeders: f.entry_ids.length, center: f.subject_account_id, downstream })}
      </p>
    );
  }
  if (f.kind === "fanout") {
    return <p>{t("alert.hypothesis.fanout", { source: f.subject_account_id, count: f.exit_ids.length })}</p>;
  }
  if (f.kind === "cycle") {
    return <p>{t("alert.hypothesis.cycle", { episodes: Number(f.features.episodes ?? 0), count: f.member_ids.length })}</p>;
  }
  return (
    <p>
      {t("alert.hypothesis.chain", {
        hops: Number(f.features.hops ?? f.member_ids.length - 1),
        from: f.member_ids[0] ?? "",
        to: f.member_ids[f.member_ids.length - 1] ?? "",
      })}
    </p>
  );
}

export function Investigation() {
  const { alertId = "" } = useParams();
  const alert = useApi(`alert:${alertId}`, (s) => api.get<AlertDetail>(`/api/v1/alerts/${alertId}`, undefined, s));
  const chain = useApi(`chain:${alertId}`, (s) => api.get<EvidenceChain>(`/api/v1/alerts/${alertId}/evidence`, undefined, s));
  const [highlight, setHighlight] = useState<{ code: string; ids: Set<string> } | null>(null);
  const [openedCase, setOpenedCase] = useState<string | null>(null);

  const graph = useMemo(
    () => (alert.data && chain.data ? buildFormationGraph(alert.data, chain.data.transactions, highlight?.ids ?? new Set()) : null),
    [alert.data, chain.data, highlight],
  );

  if (alert.error) return <ErrorState error={alert.error} onRetry={alert.reload} />;
  if (!alert.data) return <Loading rows={6} />;
  const a = alert.data;
  const f = a.formation;
  const temporal = a.evidence.find((e) => e.reason_code.startsWith("TEMPORAL_"));
  const structural = a.evidence.find((e) => e.kind === "graph_fact");
  const limitations = [...new Set([...a.coverage.limitations, ...(temporal?.limitations ?? [])])];
  const caseId = a.case_id ?? openedCase;

  function toggleHighlight(rc: ReasonCode) {
    const ev = evidenceForReason(rc.code, a.evidence);
    if (!ev) return;
    setHighlight((h) => (h?.code === rc.code ? null : { code: rc.code, ids: new Set(ev.transaction_ids) }));
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div className="stack stack--sm">
          <Link to="/alerts" className="subtle">
            ← {t("alerts.title")}
          </Link>
          <h1>
            {kindLabel(f.kind)} · <AccountId id={f.subject_account_id} />
          </h1>
          <div className="row">
            <BandBadge band={a.risk.band} />
            <EvidenceBadge status={a.temporal_status} />
            <span className="subtle">
              {a.risk.priority !== null ? `${t("alert.priority")}: ${a.risk.priority}/100` : `${t("alert.priority")}: —`} ·{" "}
              {t("alert.priorityHint")}
            </span>
          </div>
        </div>
      </div>

      <div className="investigation">
        <div className="investigation__col">
          <Panel title={t("alert.hypothesis")} id="hypothesis">
            <div className="stack">
              <Hypothesis alert={a} />
              <div className="stack stack--sm">
                <h3>{t("alert.reasons")}</h3>
                <p className="subtle">{t("alert.reasonsHint")}</p>
                <ul className="reason-list" data-testid="reasons">
                  {a.risk.reason_codes.map((rc) => {
                    const ev = evidenceForReason(rc.code, a.evidence);
                    const active = highlight?.code === rc.code;
                    return (
                      <li key={rc.code} className="reason">
                        <span className={`reason__mark reason__mark--${reasonPolarity(rc.code)}`} aria-hidden="true" />
                        <div className="reason__body">
                          <span>{reasonText(rc, f.currency)}</span>
                          {ev && ev.transaction_ids.length > 0 && (
                            <button type="button" className="btn btn--sm btn--ghost" aria-pressed={active} onClick={() => toggleHighlight(rc)}>
                              {active ? t("alert.clearHighlight") : t("alert.highlightTx")}
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <p className="subtle">
                  {t("alert.families")}: {a.risk.supported_families.map((x) => tDynamic("family.", x)).join(", ") || "—"}.{" "}
                  {a.risk.missing_families.length > 0 &&
                    t("alert.missingFamilies", { list: a.risk.missing_families.map((x) => tDynamic("family.", x)).join(", ") })}
                </p>
              </div>
            </div>
          </Panel>

          <Panel title={t("alert.graph")} hint={t("alert.graphHint")} id="formation-graph">
            {chain.error && <ErrorState error={chain.error} onRetry={chain.reload} />}
            {!graph && !chain.error && <Loading rows={3} />}
            {graph && (
              <div className="stack stack--sm">
                <GraphCanvas nodes={graph.nodes} edges={graph.edges} layout={f.kind === "chain" ? "breadthfirst" : "preset"} selectedNode={f.subject_account_id} />
                <GraphLegend roles={graph.roles} />
              </div>
            )}
          </Panel>

          {temporal && <TemporalPanel ev={temporal} currency={f.currency} />}

          <Panel
            title={t("alert.evidenceTx")}
            hint={t("alert.evidenceTxHint")}
            id="evidence-tx"
            actions={highlight ? <span className="badge">{t("alert.highlighted", { count: highlight.ids.size })}</span> : undefined}
          >
            {chain.data ? (
              <TxTable rows={chain.data.transactions} highlight={highlight?.ids} caption={t("alert.evidenceTx")} limit={15} />
            ) : (
              <Loading rows={4} />
            )}
          </Panel>
        </div>

        <div className="investigation__col">
          <CasePanel alertId={a.id} caseId={caseId} onCaseOpened={(id) => setOpenedCase(id)} />

          <Panel title={t("alert.counter")} hint={t("alert.counterHint")} id="limitations">
            <ul className="reason-list" data-testid="limitations">
              {limitations.map((l) => (
                <li key={l} className="reason">
                  <span className="reason__mark reason__mark--limit" aria-hidden="true" />
                  <span>{tDynamic("lim.", l)}</span>
                </li>
              ))}
            </ul>
            {a.coverage.boundary_accounts.length > 0 && (
              <div className="callout" style={{ marginTop: "var(--s-3)" }}>
                {t("network.boundary")}:{" "}
                {a.coverage.boundary_accounts.map((acc) => (
                  <span key={acc}>
                    <AccountId id={acc} />{" "}
                  </span>
                ))}
              </div>
            )}
          </Panel>

          <Panel title={t("alert.dataRequests")} hint={t("alert.dataRequestsHint")} id="data-requests">
            {a.coverage.data_requests.length === 0 ? (
              <p className="muted">{t("alert.noDataRequests")}</p>
            ) : (
              <ol className="steps">
                {a.coverage.data_requests.map((r, i) => (
                  <li key={`${r.type}-${i}`} className="step">
                    <span className="step__n" aria-hidden="true">
                      {i + 1}
                    </span>
                    <div>
                      <strong>{tDynamic("nbdr.", r.type)}</strong>
                      <div className="subtle">
                        {tDynamic("nbdr.res.", r.expected_resolution)} · {t("nbdr.subjects", { count: r.subject_ids.length })}
                        {r.proposed_window && ` · ${t("nbdr.window", { from: formatDate(r.proposed_window[0]!), to: formatDate(r.proposed_window[1]!) })}`}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Panel>

          <Panel title={t("alert.provenance")} id="provenance">
            <dl className="kv">
              <dt>{t("alert.detector")}</dt>
              <dd>
                <code className="mono">
                  {f.detector_id} · {f.detector_version}
                </code>
              </dd>
              <dt>{t("command.policy")}</dt>
              <dd>
                <code className="mono">{a.risk.policy_version}</code>
              </dd>
              <dt>{t("alert.snapshot")}</dt>
              <dd>
                <code className="mono" title={a.snapshot.id}>
                  {shortId(a.snapshot.id)}
                </code>
              </dd>
              <dt>{t("command.window")}</dt>
              <dd>
                {formatDate(f.window_start)} — {formatDate(f.window_end)}
              </dd>
              {structural && (
                <>
                  <dt>{t("alert.thresholds")}</dt>
                  <dd>
                    <code className="mono">{Object.entries(structural.thresholds).map(([k, v]) => `${k}=${String(v)}`).join(", ")}</code>
                  </dd>
                </>
              )}
            </dl>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function TemporalPanel({ ev, currency }: { ev: EvidenceItem; currency: string }) {
  const o = ev.observations as Record<string, unknown>;
  const lagDays = typeof o.lag_days_min === "number" ? t("temporal.lagDays", { min: Number(o.lag_days_min), max: Number(o.lag_days_max) }) : t("temporal.noLag");
  const lagSec = typeof o.lag_seconds_min === "number" ? t("temporal.lagSeconds", { min: Number(o.lag_seconds_min), max: Number(o.lag_seconds_max) }) : null;
  return (
    <Panel title={t("alert.temporal")} hint={t("alert.temporalHint")} id="temporal" actions={<EvidenceBadge status={String(o.status)} />}>
      <dl className="kv" data-testid="temporal-facts">
        <dt>{t("temporal.entry")}</dt>
        <dd>
          <Money minor={String(o.entry_minor)} currency={currency} />
        </dd>
        <dt>{t("temporal.strict")}</dt>
        <dd>
          <Money minor={String(o.strict_compatible_minor)} currency={currency} />
        </dd>
        <dt>{t("temporal.possible")}</dt>
        <dd>
          <Money minor={String(o.possible_compatible_minor)} currency={currency} />
        </dd>
        <dt>{t("temporal.share")}</dt>
        <dd>{formatBp(Number(o.compatible_fraction_bp))}</dd>
        <dt>{t("temporal.lag")}</dt>
        <dd>{lagSec ?? lagDays}</dd>
        <dt>{t("temporal.uncertain")}</dt>
        <dd>{String(o.uncertain_transition_count)}</dd>
        <dt>{t("temporal.precision")}</dt>
        <dd>{precisionLabel(String(o.time_precision))}</dd>
      </dl>
    </Panel>
  );
}
