import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { useCan } from "../../app/auth";
import { SegmentedMeter } from "../../components/charts/Progress";
import { GraphCanvas, GraphLegend, type GraphEdgeSpec, type NodeRole } from "../../components/graph/GraphCanvas";
import { AccountId, BandBadge, CaseStatusBadge, Disclosure, ErrorState, EvidenceBadge, Icon, Loading, Panel, TxTable } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate, shortId } from "../../lib/format";
import { t } from "../../lib/i18n";
import type { AlertDetail, EvidenceChain, ReasonCode } from "../../lib/types";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { useApi } from "../../lib/useApi";
import { alertTitle, formationTitle } from "../alerts/alertText";
import { CasePanel, useOpenCase } from "./CasePanel";
import { AccountView, EdgeView, SummaryView, type Highlight, type Selection } from "./ContextPanel";
import { evidenceForReason, evidenceOfFamily } from "./evidence";
import { EvidenceTimeline } from "./EvidenceTimeline";
import { buildFormationGraph } from "./formationGraph";
import { PeerCard, TemporalCard } from "./SignalCards";

export function Investigation() {
  const { alertId = "" } = useParams();
  const alert = useApi(`alert:${alertId}`, (s) => api.get<AlertDetail>(`/api/v1/alerts/${alertId}`, undefined, s));
  const chain = useApi(`chain:${alertId}`, (s) => api.get<EvidenceChain>(`/api/v1/alerts/${alertId}/evidence`, undefined, s));

  if (alert.error) return <ErrorState error={alert.error} onRetry={alert.reload} />;
  if (!alert.data)
    return (
      <div className="page">
        <Loading rows={8} label={t("alert.loading")} />
      </div>
    );
  return <Workspace key={alert.data.id} alert={alert.data} chain={chain.data} chainError={chain.error} reloadChain={chain.reload} reloadAlert={alert.reload} />;
}

function Workspace({
  alert: a,
  chain,
  chainError,
  reloadChain,
  reloadAlert,
}: {
  alert: AlertDetail;
  chain: EvidenceChain | null;
  chainError: ReturnType<typeof useApi>["error"];
  reloadChain: () => void;
  reloadAlert: () => void;
}) {
  const f = a.formation;
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [openedCase, setOpenedCase] = useState<string | null>(null);
  const caseId = a.case_id ?? openedCase;
  const canAct = useCan("analyst");
  const opener = useOpenCase(a.id, (id) => {
    setOpenedCase(id);
    reloadAlert();
  });
  const txs = chain?.transactions ?? [];

  // The graph depends only on the evidence; highlight and selection are applied as styles.
  // Phones have a portrait stage and show the context panel below the graph instead of beside it.
  const phone = useMediaQuery("(max-width: 767px)");
  const stacked = useMediaQuery("(max-width: 1099px)");
  const graph = useMemo(() => (chain ? buildFormationGraph(a, chain.transactions, new Set(), { portrait: phone }) : null), [a, chain, phone]);
  const roles = useMemo(() => new Map<string, NodeRole>(graph?.nodes.map((n) => [n.id, n.role]) ?? []), [graph]);
  const highlightEdges = useMemo(() => {
    if (!highlight || !graph) return undefined;
    return new Set(graph.edges.filter((e) => e.txIds?.some((id) => highlight.ids.has(id))).map((e) => e.id));
  }, [highlight, graph]);

  const toggleHighlight = useCallback(
    (rc: ReasonCode) => {
      const ev = evidenceForReason(rc.code, a.evidence);
      if (!ev) return;
      setHighlight((h) => (h?.code === rc.code ? null : { code: rc.code, ids: new Set(ev.transaction_ids) }));
    },
    [a.evidence],
  );
  const selectAccount = useCallback((id: string | null) => setSelection(id ? { type: "account", id } : null), []);
  const selectEdge = useCallback((e: GraphEdgeSpec | null) => setSelection(e ? { type: "edge", edge: e } : null), []);

  const temporal = evidenceOfFamily("temporal", a.evidence);
  const structural = evidenceOfFamily("structure", a.evidence);
  const peer = evidenceOfFamily("peer", a.evidence);
  const priority = a.risk.priority;

  return (
    <div className="page page--investigation">
      <header className="inv-head">
        <Link to="/alerts" className="page-head__back">
          <Icon name="arrowLeft" size={16} />
          {t("alerts.title")}
        </Link>
        <div className="inv-head__row">
          <div className="inv-head__main">
            <h1>{alertTitle(a)}</h1>
            <div className="inv-head__badges">
              <BandBadge band={a.risk.band} />
              <EvidenceBadge status={a.temporal_status} />
              {a.case_status && <CaseStatusBadge status={a.case_status} />}
              {!a.in_latest_snapshot && <span className="badge">{t("alerts.notInLatest")}</span>}
            </div>
            <dl className="inv-head__facts">
              <div>
                <dt>{t("alert.center")}</dt>
                <dd>
                  <AccountId id={f.subject_account_id} />
                </dd>
              </div>
              <div>
                <dt>{t("alert.scope")}</dt>
                <dd className="num">
                  {t("alerts.accounts", { count: f.member_count })} · {t("alerts.transactions", { count: a.transaction_count })}
                </dd>
              </div>
              <div>
                <dt>{t("command.window")}</dt>
                <dd className="num">
                  {formatDate(f.window_start)} — {formatDate(f.window_end)}
                </dd>
              </div>
              {a.related_alerts && a.related_alerts.length > 0 && (
                <div className="inv-head__related">
                  <dt title={t("alert.relatedHint")}>{t("alert.related")}</dt>
                  <dd>
                    <ul className="related-alerts" data-testid="related-alerts">
                      {a.related_alerts.map((r) => (
                        <li key={r.id}>
                          <Link to={`/alerts/${r.id}`} className="related-alerts__link">
                            <BandBadge band={r.band} size="sm" />
                            <span>{formationTitle(r.kind, r.subject_account_id)}</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </dd>
                </div>
              )}
            </dl>
          </div>
          <div className="inv-head__side">
            <div className="inv-head__priority">
              <div className="inv-head__priority-top">
                <span>{t("alert.priority")}</span>
                <strong className="num">{priority !== null ? t("alert.priorityValue", { n: priority }) : "—"}</strong>
              </div>
              <SegmentedMeter
                value={priority}
                max={100}
                label={t("alert.priority")}
                valueText={priority !== null ? t("alert.priorityValue", { n: priority }) : t("alert.priorityNone")}
                tone={a.risk.band}
              />
              <span className="inv-head__priority-hint">{t("alert.priorityHint")}</span>
            </div>
            {caseId ? (
              <a className="btn" href="#case">
                <Icon name="cases" size={16} />
                {t("case.toDecision")}
              </a>
            ) : canAct ? (
              <button type="button" className="btn btn--primary" disabled={opener.opening} data-testid="open-case" onClick={() => void opener.open()}>
                <Icon name="cases" size={16} />
                {opener.opening ? t("case.opening") : t("case.open")}
              </button>
            ) : null}
          </div>
        </div>
        {opener.error && <ErrorState error={opener.error} />}
      </header>

      <div className="workspace">
        <section className="workspace__stage" id="formation-graph" aria-labelledby="graph-title">
          <div className="stage-head">
            <div>
              <h2 id="graph-title">{t("alert.graph")}</h2>
              <p className="panel__hint">{t("alert.graphHint")}</p>
            </div>
            {highlight && (
              <button type="button" className="chip chip--active" onClick={() => setHighlight(null)}>
                {t("alert.highlighted", { count: highlight.ids.size })}
                <Icon name="close" size={14} />
              </button>
            )}
          </div>
          {chainError && <ErrorState error={chainError} onRetry={reloadChain} />}
          {!graph && !chainError && <div className="graph-stage graph-stage--loading" aria-busy="true" />}
          {graph && (
            <GraphCanvas
              nodes={graph.nodes}
              edges={graph.edges}
              layout="preset"
              highlightEdges={highlightEdges}
              selectedNode={selection?.type === "account" ? selection.id : null}
              selectedEdge={selection?.type === "edge" ? selection.edge.id : null}
              onSelectNode={selectAccount}
              onSelectEdge={selectEdge}
              overlay={<GraphLegend roles={graph.roles} highlighted={!!highlight} />}
            />
          )}
          <p className="stage-hint">{t(stacked ? "alert.stageHintStacked" : "alert.stageHint")}</p>
        </section>

        <aside className="workspace__side panel" aria-label={t("ctx.label")} aria-live="polite">
          {selection?.type === "account" ? (
            <AccountView key={selection.id} alert={a} id={selection.id} role={roles.get(selection.id)} txs={txs} onBack={() => setSelection(null)} />
          ) : selection?.type === "edge" ? (
            <EdgeView key={selection.edge.id} alert={a} edge={selection.edge} txs={txs} onBack={() => setSelection(null)} />
          ) : (
            <SummaryView alert={a} highlight={highlight} onHighlight={toggleHighlight} roles={roles} onSelectAccount={selectAccount} />
          )}
        </aside>

        <div className="workspace__evidence">
          <Panel title={t("timeline.title")} hint={t("timeline.hint")} id="timeline">
            {chain ? (
              <EvidenceTimeline txs={txs} center={f.subject_account_id} windowStart={f.window_start} windowEnd={f.window_end} highlight={highlight?.ids} />
            ) : (
              <Loading rows={3} />
            )}
          </Panel>

          <Panel
            title={t("alert.evidenceTx")}
            hint={t("alert.evidenceTxHint")}
            id="evidence-tx"
            flush
            actions={highlight ? <span className="badge badge--accent">{t("alert.highlighted", { count: highlight.ids.size })}</span> : undefined}
          >
            {chain ? (
              <TxTable
                rows={txs}
                highlight={highlight?.ids}
                caption={t("alert.evidenceTx")}
                limit={15}
                selectedPair={selection?.type === "edge" ? { source: selection.edge.source, target: selection.edge.target } : null}
              />
            ) : (
              <div className="panel__body">
                <Loading rows={4} />
              </div>
            )}
          </Panel>

          {(temporal || peer) && (
            <div className="signal-grid">
              {temporal && <TemporalCard ev={temporal} currency={f.currency} />}
              {peer && <PeerCard ev={peer} currency={f.currency} />}
            </div>
          )}

          <Disclosure summary={t("alert.provenance")} id="provenance">
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
              <dt>{t("alert.revision")}</dt>
              <dd className="num">{a.revision}</dd>
              {structural && (
                <>
                  <dt>{t("alert.thresholds")}</dt>
                  <dd>
                    <code className="mono">
                      {Object.entries(structural.thresholds)
                        .map(([k, v]) => `${k}=${String(v)}`)
                        .join(", ")}
                    </code>
                  </dd>
                </>
              )}
            </dl>
          </Disclosure>
        </div>

        <div className="workspace__decision">
          <CasePanel caseId={caseId} onOpen={() => void opener.open()} opening={opener.opening} onChanged={reloadAlert} />
        </div>
      </div>
    </div>
  );
}
