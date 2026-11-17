import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useDataset } from "../../app/dataset";
import { GraphCanvas, GraphLegend, type GraphEdgeSpec, type GraphNodeSpec } from "../../components/graph/GraphCanvas";
import { AccountId, BandBadge, Empty, ErrorState, EvidenceBadge, Loading, Money, NoDataset, Panel, TxTable } from "../../components/ui";
import { api } from "../../lib/api";
import { shortId } from "../../lib/format";
import { t, type MessageKey } from "../../lib/i18n";
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
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{t("network.title")}</h1>
          <p>{t("network.subtitle")}</p>
        </div>
      </div>
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
              className="row"
              style={{ alignItems: "flex-end" }}
              onSubmit={(e) => {
                e.preventDefault();
                search(draft);
              }}
            >
              <label className="field" style={{ flex: "1 1 260px" }}>
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
                {t("network.go")}
              </button>
            </form>
          </Panel>
          {!account && <Empty title={t("network.hint")} />}
          {account && (summary.loading || hood.loading) && !summary.data && <Loading />}
          {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
          {summary.data && !summary.data.found && (
            <Panel>
              <Empty title={t("network.notFound", { id: account, snapshot: shortId(snapshotId) })} />
            </Panel>
          )}
          {summary.data?.found && (
            <div className="investigation">
              <div className="stack">
                <Panel title={t("network.title")} id="neighborhood">
                  {hood.error && <ErrorState error={hood.error} onRetry={hood.reload} />}
                  {graph && (
                    <div className="stack stack--sm">
                      {hood.data?.truncated && (
                        <div className="callout callout--warn">
                          {t("network.truncated", { nodes: hood.data.limits.max_nodes ?? 0, edges: hood.data.limits.max_edges ?? 0 })}
                        </div>
                      )}
                      <GraphCanvas
                        nodes={graph.nodes}
                        edges={graph.edges}
                        layout="cose"
                        tall
                        selectedNode={account}
                        onSelectNode={(id) => {
                          setDraft(id);
                          search(id);
                        }}
                        onSelectEdge={setEdge}
                      />
                      <GraphLegend roles={["subject", "member", "boundary"]} />
                    </div>
                  )}
                </Panel>
                <Panel title={edge ? t("network.edgeTx", { from: shortId(edge.source, 6), to: shortId(edge.target, 6) }) : t("network.edges")}>
                  {!edge && hood.data && <EdgeTable hood={hood.data} onSelect={setEdge} />}
                  {edge && (
                    <div className="stack stack--sm">
                      <div>
                        <button type="button" className="btn btn--sm btn--ghost" onClick={() => setEdge(null)}>
                          ← {t("network.edges")}
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
      <div className="stack">
        <div className="stack stack--sm">
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
        <div className="stack stack--sm">
          <h3>{t("network.formations")}</h3>
          {summary.formations.length === 0 && <p className="muted">{t("network.noFormations")}</p>}
          <ul className="reason-list">
            {summary.formations.map((f) => (
              <li key={f.formation_id} className="row" style={{ justifyContent: "space-between" }}>
                <span>
                  {t(f.kind === "funnel" ? "kind.funnelShort" : "kind.chainShort")} · {t(`network.role.${f.role}` as MessageKey)}
                </span>
                <span className="row">
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
