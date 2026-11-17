import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { GraphCanvas, GraphLegend, type GraphEdgeSpec, type GraphNodeSpec } from "../../components/graph/GraphCanvas";
import { AccountId, BandBadge, Empty, ErrorState, EvidenceBadge, Icon, Loading, Money, NoDataset, PageHeader, Panel, TxTable } from "../../components/ui";
import { api } from "../../lib/api";
import { shortId } from "../../lib/format";
import { t, tDynamic, type MessageKey } from "../../lib/i18n";
import type { AccountSummary, Neighborhood, TransactionPage } from "../../lib/types";
import { useApi } from "../../lib/useApi";

export function NetworkExplorer() {
  const { active } = useDataset();
  const snapshotId = active?.latest_snapshot?.id ?? null;
  const [params, setParams] = useSearchParams();
  const account = params.get("account") ?? "";
  const depth = Number(params.get("depth") ?? "1") === 2 ? 2 : 1;
  const [draft, setDraft] = useState(account);
  const [edge, setEdge] = useState<GraphEdgeSpec | null>(null);

  const key = snapshotId && account ? `${snapshotId}:${account}:${depth}` : null;
  const summary = useApi(key && `acc:${key}`, (s) =>
    api.get<AccountSummary>(`/api/v1/snapshots/${snapshotId}/accounts/${encodeURIComponent(account)}`, undefined, s),
  );
  const hood = useApi(key && `hood:${key}`, (s) =>
    api.get<Neighborhood>(`/api/v1/snapshots/${snapshotId}/neighborhood`, { account_id: account, depth, max_nodes: 120 }, s),
  );
  const edgeKey = snapshotId && edge ? `edge:${snapshotId}:${edge.source}:${edge.target}` : null;
  const edgeTx = useApi(edgeKey, (s) =>
    api.get<TransactionPage>(`/api/v1/snapshots/${snapshotId}/transactions`, { account_id: edge!.source, counterparty_id: edge!.target, limit: 200 }, s),
  );

  const graph = useMemo(() => {
    if (!hood.data) return null;
    const nodes: GraphNodeSpec[] = hood.data.nodes.map((n) => ({
      id: n.account_id,
      role: n.is_boundary ? "boundary" : n.account_id === hood.data!.center ? "subject" : n.hop === 1 ? "member" : "context",
    }));
    const edges: GraphEdgeSpec[] = hood.data.edges.map((e) => ({
      id: `e:${e.sender}:${e.receiver}:${e.currency}`,
      source: e.sender,
      target: e.receiver,
      amountMinor: e.amount_minor,
      currency: e.currency,
      count: e.n_transactions,
    }));
    return { nodes, edges };
  }, [hood.data]);

  function search(next: string, nextDepth = depth) {
    const p = new URLSearchParams();
    if (next.trim()) p.set("account", next.trim());
    if (nextDepth === 2) p.set("depth", "2");
    setEdge(null);
    setParams(p);
  }

  return (
    <div className="page">
      <PageHeader title={t("network.title")} description={t("network.subtitle")} />
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
            <form
              className="network-search"
              onSubmit={(e) => {
                e.preventDefault();
                search(draft);
              }}
            >
              <label className="field network-search__id">
                {t("network.search")}
                <input className="input mono" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false} autoComplete="off" name="account" />
              </label>
              <label className="field">
                {t("network.depth")}
                <select className="select" value={depth} onChange={(e) => search(account || draft, Number(e.target.value))}>
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                </select>
              </label>
              <button type="submit" className="btn btn--primary" disabled={!draft.trim()}>
                <Icon name="search" size={16} />
                {t("network.go")}
              </button>
            </form>
          </Panel>
          {!account && (
            <Panel>
              <Empty title={t("network.hint")} icon="network" />
            </Panel>
          )}
          {account && (summary.loading || hood.loading) && !summary.data && <Loading />}
          {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
          {summary.data && !summary.data.found && (
            <Panel>
              <Empty title={t("network.notFound", { id: account, snapshot: shortId(snapshotId) })} />
            </Panel>
          )}
          {summary.data?.found && (
            <div className="network-layout">
              <div className="network-layout__main">
                <Panel title={t("network.graph")} id="neighborhood">
                  {hood.error && <ErrorState error={hood.error} onRetry={hood.reload} />}
                  {graph && (
                    <div className="network-graph">
                      {hood.data?.truncated && (
                        <div className="callout callout--warn">
                          {t("network.truncated", { nodes: hood.data.limits.max_nodes ?? 0, edges: hood.data.limits.max_edges ?? 0 })}
                        </div>
                      )}
                      <GraphCanvas
                        nodes={graph.nodes}
                        edges={graph.edges}
                        layout="cose"
                        edgeLabels={false}
                        className="graph-stage--tall"
                        selectedNode={account}
                        selectedEdge={edge?.id ?? null}
                        onSelectNode={(id) => {
                          if (!id) return;
                          setDraft(id);
                          search(id);
                        }}
                        onSelectEdge={setEdge}
                        overlay={<GraphLegend roles={["subject", "member", "context", "boundary"]} />}
                      />
                    </div>
                  )}
                </Panel>
                <Panel title={edge ? t("network.edgeTx", { from: shortId(edge.source, 6), to: shortId(edge.target, 6) }) : t("network.edges")}>
                  {!edge && hood.data && <EdgeTable hood={hood.data} onSelect={setEdge} />}
                  {edge && (
                    <div className="network-edge">
                      <div>
                        <button type="button" className="link-btn" onClick={() => setEdge(null)}>
                          <Icon name="arrowLeft" size={16} />
                          {t("network.edges")}
                        </button>
                      </div>
                      {edgeTx.error && <ErrorState error={edgeTx.error} onRetry={edgeTx.reload} />}
                      {edgeTx.data ? <TxTable rows={edgeTx.data.items} caption={t("network.edges")} limit={25} /> : <Loading rows={3} />}
                    </div>
                  )}
                </Panel>
              </div>
              <AccountPanel summary={summary.data} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function EdgeTable({ hood, onSelect }: { hood: Neighborhood; onSelect: (e: GraphEdgeSpec) => void }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="visually-hidden">{t("network.edges")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("common.from")}</th>
            <th scope="col">{t("common.to")}</th>
            <th scope="col" className="right">
              {t("common.amount")}
            </th>
            <th scope="col" className="right">
              n
            </th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          {hood.edges.map((e) => {
            const spec: GraphEdgeSpec = {
              id: `e:${e.sender}:${e.receiver}:${e.currency}`,
              source: e.sender,
              target: e.receiver,
              amountMinor: e.amount_minor,
              currency: e.currency,
              count: e.n_transactions,
            };
            return (
              <tr key={spec.id}>
                <td>
                  <AccountId id={e.sender} />
                </td>
                <td>
                  <AccountId id={e.receiver} />
                </td>
                <td className="right">
                  <Money minor={e.amount_minor} currency={e.currency} />
                </td>
                <td className="right num">{e.n_transactions}</td>
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

function AccountPanel({ summary }: { summary: AccountSummary }) {
  return (
    <Panel title={t("network.summary")} id="account-summary">
      <div className="ctx">
        <div className="ctx__section">
          <AccountId id={summary.account_id} link={false} />
          {summary.is_boundary && <span className="badge badge--insufficient_evidence">{t("network.boundary")}</span>}
        </div>
        <dl className="kv">
          <dt>{t("network.in")}</dt>
          <dd>
            <Money minor={summary.incoming_minor} /> · {summary.incoming_count} · {t("network.counterparties", { count: summary.distinct_senders })}
          </dd>
          <dt>{t("network.out")}</dt>
          <dd>
            <Money minor={summary.outgoing_minor} /> · {summary.outgoing_count} · {t("network.counterparties", { count: summary.distinct_receivers })}
          </dd>
        </dl>
        <div className="ctx__section">
          <h3 className="ctx__label">{t("network.formations")}</h3>
          {summary.formations.length === 0 && <p className="ctx__note">{t("network.noFormations")}</p>}
          <ul className="reason-list">
            {summary.formations.map((f) => (
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
    </Panel>
  );
}
