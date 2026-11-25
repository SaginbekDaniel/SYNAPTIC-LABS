import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useDataset } from "../../app/dataset";
import { GraphCanvas, type GraphEdgeSpec } from "../../components/graph/GraphCanvas";
import type { GraphController } from "../../components/graph/controller";
import { AccountId, BandBadge, Empty, ErrorState, EvidenceBadge, Icon, Loading, Money, NoDataset, PageHeader, Panel, Segmented, TxTable } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime, shortId } from "../../lib/format";
import { t, tDynamic, type MessageKey } from "../../lib/i18n";
import { FORMATION_KINDS, type AccountSummary, type Band, type FormationKind, type InvestigationEdge, type InvestigationGraph, type TemporalStatus, type TransactionPage } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { GestureLayer, GestureToggle, useGestureSession } from "../gestures/GestureControl";
import { BAND_ORDER, DEFAULT_FILTERS, edgeId, edgeStatus, formationMembers, mergeExpansion, toCanvas, type ClientFilters } from "./graphModel";

type Mode = "overview" | "local";
type View = "graph" | "table";
const TEMPORAL: TemporalStatus[] = ["supported", "possible_ambiguous", "contradicted", "unavailable"];

function multi<T extends string>(params: URLSearchParams, key: string, allowed: readonly T[]): T[] {
  return params.getAll(key).filter((v): v is T => (allowed as readonly string[]).includes(v));
}

/**
 * Graph workspace: a bounded, server-ranked overview of the snapshot's formations and an exact
 * 1–2 hop neighbourhood for any account. Mode, account, depth and server filters live in the URL
 * (no tokens, no records); client-side filters only hide drawn edges.
 */
export function GraphWorkspace() {
  const { active } = useDataset();
  const snapshotId = active?.latest_snapshot?.id ?? null;
  const [params, setParams] = useSearchParams();
  const account = params.get("account") ?? "";
  const mode: Mode = account ? "local" : params.get("mode") === "local" ? "local" : "overview";
  const depth = params.get("depth") === "2" ? 2 : 1;
  const bands = multi(params, "band", BAND_ORDER);
  const kinds = multi(params, "kind", FORMATION_KINDS);
  const [draft, setDraft] = useState(account);
  const [view, setView] = useState<View>("graph");
  const [filters, setFilters] = useState<ClientFilters>(DEFAULT_FILTERS);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<InvestigationEdge | null>(null);
  const [emphasis, setEmphasis] = useState<string | null>(null);
  const [controller, setController] = useState<GraphController | null>(null);
  const gestures = useGestureSession(controller);
  const activeFilters = bands.length + kinds.length + filters.temporal.length + (filters.edgeScope === "evidence" ? 1 : 0) + (filters.currency ? 1 : 0);
  // Closed unless a filter is active, on every screen size: the graph comes first (H-23). The summary shows how
  // many filters are active, so a filtered view is never mistaken for the whole snapshot.
  const [filtersOpen, setFiltersOpen] = useState(activeFilters > 0);

  useEffect(() => setDraft(account), [account]);

  const key = snapshotId && (mode === "overview" || account) ? `g:${snapshotId}:${mode}:${account}:${depth}:${bands.join(",")}:${kinds.join(",")}` : null;
  const base = useApi(key, (s) =>
    api.get<InvestigationGraph>(
      `/api/v1/snapshots/${snapshotId}/graph`,
      { mode, account_id: mode === "local" ? account : undefined, depth: mode === "local" ? depth : undefined, band: bands, kind: kinds, max_nodes: 200 },
      s,
    ),
  );

  // The workspace starts from the fetched view and grows through expansions. Any new base view
  // (dataset, snapshot, mode or filter change) starts a new generation and drops pending expansions.
  const [workspace, setWorkspaceState] = useState<InvestigationGraph | null>(null);
  // Mirrors the latest workspace synchronously, so two expansions resolving back to back both merge
  // into the newest graph rather than into a render-stale copy.
  const workspaceRef = useRef<InvestigationGraph | null>(null);
  const setWorkspace = useCallback((g: InvestigationGraph | null) => {
    workspaceRef.current = g;
    setWorkspaceState(g);
  }, []);
  const [notice, setNotice] = useState<"snapshot_changed" | "budget" | "expand_failed" | null>(null);
  const generation = useRef(0);
  const pending = useRef(new Set<AbortController>());
  useEffect(() => {
    generation.current += 1;
    pending.current.forEach((c) => c.abort());
    pending.current.clear();
    setWorkspace(base.data);
    setSelectedNode(null);
    setSelectedEdge(null);
    setEmphasis(null);
    setNotice(null);
  }, [base.data, setWorkspace]);
  useEffect(() => () => pending.current.forEach((c) => c.abort()), []);

  const expand = useCallback(
    (id: string) => {
      if (!snapshotId) return;
      const gen = generation.current;
      const ctrl = new AbortController();
      pending.current.add(ctrl);
      api
        .get<InvestigationGraph>(`/api/v1/snapshots/${snapshotId}/graph`, { mode: "local", account_id: id, depth: 1, max_nodes: 120 }, ctrl.signal)
        .then((next) => {
          if (gen !== generation.current) return; // a newer view replaced the one this was for
          const cur = workspaceRef.current;
          if (!cur) return;
          const merged = mergeExpansion(cur, next);
          if (merged.ok) setWorkspace(merged.graph);
          else setNotice(merged.reason);
        })
        .catch((e: unknown) => {
          if ((e as Error).name === "AbortError" || gen !== generation.current) return;
          setNotice("expand_failed");
        })
        .finally(() => pending.current.delete(ctrl));
    },
    [snapshotId, setWorkspace],
  );

  const canvas = useMemo(() => (workspace ? toCanvas(workspace, filters) : null), [workspace, filters]);
  const emphasisSet = useMemo(() => (workspace && emphasis ? formationMembers(workspace, emphasis) : null), [workspace, emphasis]);

  function navigate(next: { account?: string; mode?: Mode; depth?: number; bands?: Band[]; kinds?: FormationKind[] }) {
    const p = new URLSearchParams();
    const acc = next.account ?? account;
    const m = next.mode ?? (acc ? "local" : mode);
    if (m === "local" && acc) p.set("account", acc);
    if (m === "local" && !acc) p.set("mode", "local");
    if ((next.depth ?? depth) === 2 && m === "local") p.set("depth", "2");
    (next.bands ?? bands).forEach((b) => p.append("band", b));
    (next.kinds ?? kinds).forEach((k) => p.append("kind", k));
    setParams(p);
  }
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const selectEdgeSpec = (spec: GraphEdgeSpec | null) => {
    setSelectedNode(null);
    setSelectedEdge(spec ? workspace?.edges.find((e) => edgeId(e) === spec.id) ?? null : null);
  };

  return (
    <div className="page">
      <PageHeader title={t("network.title")} description={t("graphws.subtitle")} />
      {!active && (
        <Panel>
          <NoDataset />
        </Panel>
      )}
      {active && !snapshotId && (
        <Panel>
          <Empty title={t("dataset.noSnapshot")} />
        </Panel>
      )}
      {snapshotId && (
        <>
          <Panel>
            <div className="graph-toolbar">
              <Segmented<Mode>
                label={t("graphws.mode")}
                value={mode}
                options={[
                  { value: "overview", label: t("graphws.mode.overview") },
                  { value: "local", label: t("graphws.mode.local") },
                ]}
                onChange={(m) => (m === "overview" ? navigate({ mode: "overview", account: "" }) : navigate({ mode: "local" }))}
              />
              <form
                className="network-search"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (draft.trim()) navigate({ account: draft.trim(), mode: "local" });
                }}
              >
                <label className="field network-search__id">
                  {t("network.search")}
                  <input className="input mono" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} autoComplete="off" name="account" />
                </label>
                <label className="field">
                  {t("network.depth")}
                  <select className="select" value={depth} disabled={mode !== "local"} onChange={(e) => navigate({ depth: Number(e.target.value) })}>
                    <option value={1}>1</option>
                    <option value={2}>2</option>
                  </select>
                </label>
                <button type="submit" className="btn btn--primary" disabled={!draft.trim()}>
                  <Icon name="search" size={16} />
                  {t("network.go")}
                </button>
              </form>
            </div>
            <details className="graph-filters" open={filtersOpen} onToggle={(e) => setFiltersOpen(e.currentTarget.open)}>
              <summary className="graph-filters__summary">
                <Icon name="sliders" size={16} />
                {t("graphws.filters")}
                {activeFilters > 0 && <span className="graph-filters__count num">{activeFilters}</span>}
              </summary>
              <div className="graph-filters__body" role="group" aria-label={t("graphws.filters")}>
              <FilterGroup label={t("graphws.filter.band")}>
                {BAND_ORDER.map((b) => (
                  <button key={b} type="button" className="chip" aria-pressed={bands.includes(b)} onClick={() => navigate({ bands: toggle(bands, b) })}>
                    {tDynamic("band.", b)}
                  </button>
                ))}
              </FilterGroup>
              <FilterGroup label={t("graphws.filter.kind")}>
                {FORMATION_KINDS.map((k) => (
                  <button key={k} type="button" className="chip" aria-pressed={kinds.includes(k)} onClick={() => navigate({ kinds: toggle(kinds, k) })}>
                    {tDynamic("kind.", `${k}Short`)}
                  </button>
                ))}
              </FilterGroup>
              <FilterGroup label={t("graphws.filter.temporal")}>
                {TEMPORAL.map((s) => (
                  <button key={s} type="button" className="chip" aria-pressed={filters.temporal.includes(s)} onClick={() => setFilters((f) => ({ ...f, temporal: toggle(f.temporal, s) }))}>
                    {tDynamic("ev.", s)}
                  </button>
                ))}
              </FilterGroup>
              <FilterGroup label={t("graphws.filter.edges")}>
                <button type="button" className="chip" aria-pressed={filters.edgeScope === "evidence"} onClick={() => setFilters((f) => ({ ...f, edgeScope: f.edgeScope === "evidence" ? "all" : "evidence" }))}>
                  {t("graphws.filter.evidenceOnly")}
                </button>
                {canvas && canvas.currencies.length > 1 && (
                  <select className="select select--sm" aria-label={t("graphws.filter.currency")} value={filters.currency ?? ""} onChange={(e) => setFilters((f) => ({ ...f, currency: e.target.value || null }))}>
                    <option value="">{t("graphws.filter.allCurrencies")}</option>
                    {canvas.currencies.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                )}
              </FilterGroup>
              </div>
            </details>
          </Panel>

          {mode === "local" && !account && (
            <Panel>
              <Empty title={t("network.hint")} icon="network" />
            </Panel>
          )}
          {base.error && <ErrorState error={base.error} onRetry={base.reload} />}
          {key && base.loading && !workspace && <Loading rows={6} />}
          {workspace && !workspace.found && (
            <Panel>
              <Empty title={mode === "local" ? t("network.notFound", { id: account, snapshot: shortId(snapshotId) }) : t("graphws.emptyOverview")} />
            </Panel>
          )}
          {workspace?.found && canvas && (
            <div className="network-layout">
              <div className="network-layout__main">
                <Panel
                  title={mode === "local" ? t("network.graph") : t("graphws.overviewTitle")}
                  id="neighborhood"
                  actions={
                    <Segmented<View>
                      size="sm"
                      label={t("graphws.view")}
                      value={view}
                      options={[
                        { value: "graph", label: t("graphws.view.graph") },
                        { value: "table", label: t("graphws.view.table") },
                      ]}
                      onChange={setView}
                    />
                  }
                >
                  <SnapshotLine graph={workspace} />
                  {workspace.limits.reasons.some((r) => r !== "max_formations") ? (
                    <div className="callout callout--warn" data-testid="graph-truncated">
                      {t("graphws.truncated", { nodes: workspace.limits.max_nodes })}
                    </div>
                  ) : (
                    workspace.limits.formations_total > workspace.formations.length && (
                      <p className="stage-hint" data-testid="graph-truncated">
                        {t("graphws.topFormations", { shown: workspace.formations.length, total: workspace.limits.formations_total })}
                      </p>
                    )
                  )}
                  {notice && (
                    <div className="callout callout--warn" role="status">
                      {t(`graphws.notice.${notice}` as MessageKey)}
                      {notice === "snapshot_changed" && (
                        <button type="button" className="btn btn--sm" onClick={base.reload}>
                          {t("graphws.reload")}
                        </button>
                      )}
                    </div>
                  )}
                  {canvas.hiddenEdges > 0 && <p className="stage-hint">{t("graphws.hiddenEdges", { count: canvas.hiddenEdges })}</p>}
                  {view === "graph" ? (
                    <div className="network-graph">
                      <GraphCanvas
                        nodes={canvas.nodes}
                        edges={canvas.edges}
                        order={canvas.order}
                        layout="cose"
                        colorBy="band"
                        edgeLabels={false}
                        className="graph-stage--tall"
                        selectedNode={selectedNode ?? (mode === "local" ? account : null)}
                        selectedEdge={selectedEdge ? edgeId(selectedEdge) : null}
                        emphasis={emphasisSet}
                        onSelectNode={(id) => {
                          setSelectedEdge(null);
                          setSelectedNode(id);
                        }}
                        onSelectEdge={selectEdgeSpec}
                        onExpand={expand}
                        onController={setController}
                        label={t("graphws.alt", { nodes: canvas.nodes.length, edges: canvas.edges.length })}
                        controls={<GestureToggle session={gestures} />}
                      >
                        <GestureLayer session={gestures} />
                      </GraphCanvas>
                      {/* Below the stage, not over it: a legend must never hide nodes. */}
                      <WorkspaceLegend />
                    </div>
                  ) : (
                    <EdgeTable graph={workspace} edges={canvas.edges} onSelect={(e) => selectEdgeSpec(e)} />
                  )}
                  <p className="stage-hint">{t("graphws.hint")}</p>
                </Panel>
              </div>
              <aside className="network-layout__side" aria-live="polite">
                {selectedEdge ? (
                  <EdgePanel snapshotId={snapshotId} graph={workspace} edge={selectedEdge} onBack={() => setSelectedEdge(null)} />
                ) : selectedNode || (mode === "local" && account) ? (
                  <AccountPanel
                    snapshotId={snapshotId}
                    id={selectedNode ?? account}
                    centred={mode === "local" && (selectedNode ?? account) === account}
                    onCentre={(id) => navigate({ account: id, mode: "local" })}
                    onExpand={expand}
                    onBack={selectedNode ? () => setSelectedNode(null) : undefined}
                  />
                ) : (
                  <FormationsPanel graph={workspace} emphasis={emphasis} onEmphasis={setEmphasis} />
                )}
              </aside>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="graph-filters__group" role="group" aria-label={label}>
      <span className="graph-filters__label">{label}</span>
      <div className="graph-filters__chips">{children}</div>
    </div>
  );
}

function SnapshotLine({ graph }: { graph: InvestigationGraph }) {
  return (
    <p className="graph-snapshot" data-testid="graph-snapshot">
      <span title={graph.snapshot_id}>{t("graphws.snapshot", { id: shortId(graph.snapshot_id) })}</span>
      <span>{graph.policy_version}</span>
      <span title={graph.config_sha256}>{t("graphws.config", { hash: graph.config_sha256.slice(0, 8) })}</span>
      <span>{formatDateTime(graph.computed_at)}</span>
    </p>
  );
}

function WorkspaceLegend() {
  const bands: Band[] = ["critical", "high", "medium", "insufficient_evidence", "low"];
  const lines: { cls: string; key: MessageKey }[] = [
    { cls: "context", key: "graphws.legend.context" },
    { cls: "supported", key: "ev.supported" },
    { cls: "possible_ambiguous", key: "ev.possible_ambiguous" },
    { cls: "contradicted", key: "ev.contradicted" },
    { cls: "unavailable", key: "ev.unavailable" },
  ];
  return (
    <ul className="graph-legend" aria-label={t("graphws.legend")}>
      {bands.map((b) => (
        <li key={b}>
          <span className="graph-legend__dot" style={{ color: `var(--band-${b === "insufficient_evidence" ? "unresolved" : b})` }} aria-hidden="true" />
          {tDynamic("band.", b)}
        </li>
      ))}
      <li>
        <span className="graph-legend__dot graph-legend__dot--none" aria-hidden="true" />
        {t("graphws.legend.noFormation")}
      </li>
      <li>
        <span className="graph-legend__diamond" aria-hidden="true" />
        {t("graphws.legend.hub")}
      </li>
      <li>
        <span className="graph-legend__dot graph-legend__dot--dashed" style={{ color: "var(--g-boundary)" }} aria-hidden="true" />
        {t("graph.legend.boundary")}
      </li>
      {lines.map((l) => (
        <li key={l.cls}>
          <span className={`graph-legend__line graph-legend__line--${l.cls}`} aria-hidden="true" />
          {t(l.key)}
        </li>
      ))}
      <li className="graph-legend__note">{t("graphws.legend.width")}</li>
    </ul>
  );
}

function EdgeTable({ graph, edges, onSelect }: { graph: InvestigationGraph; edges: GraphEdgeSpec[]; onSelect: (e: GraphEdgeSpec) => void }) {
  const shown = new Set(edges.map((e) => e.id));
  const rows = graph.edges.filter((e) => shown.has(edgeId(e)));
  return (
    <div className="table-wrap" data-testid="graph-table">
      <table className="table">
        <caption className="visually-hidden">{t("graphws.tableCaption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("common.from")}</th>
            <th scope="col">{t("common.to")}</th>
            <th scope="col" className="right">
              {t("common.amount")}
            </th>
            <th scope="col" className="right">
              {t("graphws.col.count")}
            </th>
            <th scope="col">{t("graphws.col.evidence")}</th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => {
            const spec = edges.find((x) => x.id === edgeId(e))!;
            const status = edgeStatus(e);
            return (
              <tr key={spec.id}>
                <td>
                  <AccountId id={e.sender} link={false} compact />
                </td>
                <td>
                  <AccountId id={e.receiver} link={false} compact />
                </td>
                <td className="right">
                  <Money minor={e.amount_minor} currency={e.currency} />
                </td>
                <td className="right num">{e.n_transactions}</td>
                <td>{status ? <EvidenceBadge status={status === "mixed" ? "mixed" : status} label={status === "mixed" ? t("graphws.mixed") : undefined} /> : <span className="muted">{t("graphws.contextEdge")}</span>}</td>
                <td className="right">
                  <button type="button" className="btn btn--sm" onClick={() => onSelect(spec)}>
                    {t("common.open")}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FormationsPanel({ graph, emphasis, onEmphasis }: { graph: InvestigationGraph; emphasis: string | null; onEmphasis: (id: string | null) => void }) {
  return (
    <Panel title={t("graphws.formations")} id="graph-formations">
      {graph.formations.length === 0 ? (
        <p className="ctx__note">{t("network.noFormations")}</p>
      ) : (
        <ul className="reason-list">
          {graph.formations.map((f) => (
            <li key={f.id} className={`formation-item${emphasis === f.id ? " formation-item--active" : ""}`}>
              <span>
                {tDynamic("kind.", `${f.kind}Short`)} · <AccountId id={f.subject_account_id} link={false} compact /> · {t("graphws.accounts", { count: f.account_count })}
              </span>
              <span className="formation-item__badges">
                <EvidenceBadge status={f.temporal_status} />
                <BandBadge band={f.band} size="sm" />
                <button type="button" className="btn btn--sm" aria-pressed={emphasis === f.id} onClick={() => onEmphasis(emphasis === f.id ? null : f.id)}>
                  {t("graphws.highlight")}
                </button>
                {f.alert_id && (
                  <Link className="btn btn--sm" to={`/alerts/${f.alert_id}`}>
                    {t("common.open")}
                  </Link>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="ctx__note">{t("graphws.formationsNote")}</p>
    </Panel>
  );
}

function AccountPanel({
  snapshotId,
  id,
  centred,
  onCentre,
  onExpand,
  onBack,
}: {
  snapshotId: string;
  id: string;
  centred: boolean;
  onCentre: (id: string) => void;
  onExpand: (id: string) => void;
  onBack?: () => void;
}) {
  const summary = useApi(`acc:${snapshotId}:${id}`, (s) => api.get<AccountSummary>(`/api/v1/snapshots/${snapshotId}/accounts/${encodeURIComponent(id)}`, undefined, s));
  return (
    <Panel title={t("network.summary")} id="account-summary">
      {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
      {!summary.data && !summary.error && <Loading rows={3} />}
      {summary.data && (
        <div className="ctx">
          {onBack && (
            <button type="button" className="link-btn" onClick={onBack}>
              <Icon name="arrowLeft" size={16} />
              {t("graphws.formations")}
            </button>
          )}
          <div className="ctx__section">
            <AccountId id={summary.data.account_id} link={false} />
            {summary.data.is_boundary && <span className="badge badge--insufficient_evidence">{t("network.boundary")}</span>}
          </div>
          <div className="graph-actions">
            {!centred && (
              <button type="button" className="btn btn--sm" onClick={() => onCentre(id)}>
                {t("graphws.centre")}
              </button>
            )}
            <button type="button" className="btn btn--sm" onClick={() => onExpand(id)}>
              {t("graphws.expand")}
            </button>
          </div>
          <dl className="kv">
            <dt>{t("network.in")}</dt>
            <dd>
              <Money minor={summary.data.incoming_minor} /> · {summary.data.incoming_count} · {t("network.counterparties", { count: summary.data.distinct_senders })}
            </dd>
            <dt>{t("network.out")}</dt>
            <dd>
              <Money minor={summary.data.outgoing_minor} /> · {summary.data.outgoing_count} · {t("network.counterparties", { count: summary.data.distinct_receivers })}
            </dd>
          </dl>
          <div className="ctx__section">
            <h3 className="ctx__label">{t("network.formations")}</h3>
            {summary.data.formations.length === 0 && <p className="ctx__note">{t("network.noFormations")}</p>}
            <ul className="reason-list">
              {summary.data.formations.map((f) => (
                <li key={f.formation_id} className="formation-item">
                  <span>
                    {tDynamic("kind.", `${f.kind}Short`)} · {t(`network.role.${f.role}` as MessageKey)}
                  </span>
                  <span className="formation-item__badges">
                    <EvidenceBadge status={f.temporal_status} />
                    <BandBadge band={f.band} />
                    {f.alert_id && (
                      <Link className="btn btn--sm" to={`/alerts/${f.alert_id}`}>
                        {t("common.open")}
                      </Link>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Panel>
  );
}

function EdgePanel({ snapshotId, graph, edge, onBack }: { snapshotId: string; graph: InvestigationGraph; edge: InvestigationEdge; onBack: () => void }) {
  const txs = useApi(`etx:${snapshotId}:${edgeId(edge)}`, (s) =>
    api.get<TransactionPage>(`/api/v1/snapshots/${snapshotId}/edge-transactions`, { sender: edge.sender, receiver: edge.receiver, currency: edge.currency, limit: 200 }, s),
  );
  const formations = graph.formations.filter((f) => edge.evidence_formation_ids.includes(f.id));
  return (
    <Panel title={t("network.edgeTx", { from: shortId(edge.sender, 6), to: shortId(edge.receiver, 6) })} id="edge-detail">
      <div className="ctx">
        <button type="button" className="link-btn" onClick={onBack}>
          <Icon name="arrowLeft" size={16} />
          {t("graphws.formations")}
        </button>
        <dl className="kv">
          <dt>{t("common.from")}</dt>
          <dd>
            <AccountId id={edge.sender} link={false} />
          </dd>
          <dt>{t("common.to")}</dt>
          <dd>
            <AccountId id={edge.receiver} link={false} />
          </dd>
          <dt>{t("common.amount")}</dt>
          <dd>
            <Money minor={edge.amount_minor} currency={edge.currency} /> · {t("graphws.transfers", { count: edge.n_transactions })}
          </dd>
        </dl>
        <div className="ctx__section">
          <h3 className="ctx__label">{t("graphws.edgeEvidence")}</h3>
          {formations.length === 0 ? (
            <p className="ctx__note">{t("graphws.edgeContext")}</p>
          ) : (
            <ul className="reason-list">
              {formations.map((f) => (
                <li key={f.id} className="formation-item">
                  <span>{tDynamic("kind.", `${f.kind}Short`)}</span>
                  <span className="formation-item__badges">
                    <EvidenceBadge status={f.temporal_status} />
                    <BandBadge band={f.band} size="sm" />
                    {f.alert_id && (
                      <Link className="btn btn--sm" to={`/alerts/${f.alert_id}`}>
                        {t("common.open")}
                      </Link>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="ctx__section">
          <h3 className="ctx__label">{t("graphws.sourceTx")}</h3>
          {txs.error && <ErrorState error={txs.error} onRetry={txs.reload} />}
          {txs.data ? <TxTable rows={txs.data.items} caption={t("graphws.sourceTx")} limit={10} /> : !txs.error && <Loading rows={3} />}
        </div>
      </div>
    </Panel>
  );
}
