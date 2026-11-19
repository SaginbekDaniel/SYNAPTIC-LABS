import { Link } from "react-router-dom";
import type { GraphEdgeSpec, NodeRole } from "../../components/graph/GraphCanvas";
import { AccountId, ErrorState, Icon, Loading, Money } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate, formatEventTime, formatMoney, shortId } from "../../lib/format";
import { reasonText, t, tDynamic } from "../../lib/i18n";
import type { AccountSummary, AlertDetail, EvidenceItem, ReasonCode, Transaction } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { evidenceForReason, groupReasons, limitationsOf } from "./evidence";
import { accountFlows } from "./formationGraph";
import { CompetingExplanations } from "./Hypotheses";

export type Selection = { type: "account"; id: string } | { type: "edge"; edge: GraphEdgeSpec } | null;

export interface Highlight {
  code: string;
  ids: Set<string>;
}

function Hypothesis({ alert }: { alert: AlertDetail }) {
  const f = alert.formation;
  if (f.kind === "fan_out") {
    const onward = Number(f.features.onward_count ?? 0);
    return (
      <p className="hypothesis">
        {t("alert.hypothesis.fanOut", {
          center: f.subject_account_id,
          count: f.exit_ids.length,
          onward: onward > 0 ? t("alert.hypothesis.fanOutOnward", { count: onward }) : t("alert.hypothesis.fanOutTerminal"),
        })}
      </p>
    );
  }
  if (f.kind === "cycle") return <p className="hypothesis">{t("alert.hypothesis.cycle", { count: f.member_ids.length, start: f.subject_account_id })}</p>;
  if (f.kind === "funnel") {
    const downstream = f.exit_ids.length ? t("alert.hypothesis.funnelDown", { count: f.exit_ids.length }) : t("alert.hypothesis.funnelNoDown");
    return <p className="hypothesis">{t("alert.hypothesis.funnel", { feeders: f.entry_ids.length, center: f.subject_account_id, downstream })}</p>;
  }
  return (
    <p className="hypothesis">
      {t("alert.hypothesis.chain", {
        hops: Number(f.features.hops ?? f.member_ids.length - 1),
        from: f.member_ids[0] ?? "",
        to: f.member_ids[f.member_ids.length - 1] ?? "",
      })}
    </p>
  );
}

function ReasonItem({ rc, alert, highlight, onHighlight, tone }: { rc: ReasonCode; alert: AlertDetail; highlight: Highlight | null; onHighlight: (rc: ReasonCode) => void; tone: string }) {
  const ev = evidenceForReason(rc.code, alert.evidence);
  const active = highlight?.code === rc.code;
  return (
    <li className={`reason reason--${tone}`}>
      <span className="reason__mark" aria-hidden="true">
        <Icon name={tone === "supports" ? "check" : tone === "weakens" ? "minus" : "info"} size={14} />
      </span>
      <div className="reason__body">
        <span>{reasonText(rc, alert.formation.currency)}</span>
        {ev && ev.transaction_ids.length > 0 && (
          <button type="button" className="link-btn" aria-pressed={active} onClick={() => onHighlight(rc)}>
            {active ? t("alert.clearHighlight") : t("alert.highlightTx")}
            <span className="cell-note num">{ev.transaction_ids.length}</span>
          </button>
        )}
      </div>
    </li>
  );
}

const ROLE_KEY: Record<NodeRole, Parameters<typeof t>[0]> = {
  subject: "graph.legend.subject",
  entry: "graph.legend.entry",
  exit: "graph.legend.exit",
  member: "graph.legend.member",
  boundary: "graph.legend.boundary",
  context: "graph.legend.member",
};

export function SummaryView({
  alert,
  highlight,
  onHighlight,
  roles,
  onSelectAccount,
}: {
  alert: AlertDetail;
  highlight: Highlight | null;
  onHighlight: (rc: ReasonCode) => void;
  roles: Map<string, NodeRole>;
  onSelectAccount: (id: string) => void;
}) {
  const groups = groupReasons(alert, { withVerdict: !alert.hypotheses });
  const limitations = limitationsOf(alert);
  const requests = alert.coverage.data_requests;
  return (
    <div className="ctx">
      <section className="ctx__section">
        <h2 className="ctx__title">{t("alert.why")}</h2>
        <Hypothesis alert={alert} />
      </section>

      {alert.hypotheses && <CompetingExplanations assessment={alert.hypotheses} />}

      <section className="ctx__section" data-testid="reasons">
        <h3 className="ctx__label ctx__label--supports">{t("alert.supports")}</h3>
        <ul className="reason-list">
          {groups.supports.map((rc) => (
            <ReasonItem key={rc.code} rc={rc} alert={alert} highlight={highlight} onHighlight={onHighlight} tone="supports" />
          ))}
        </ul>
        {groups.weakens.length > 0 && (
          <>
            <h3 className="ctx__label ctx__label--weakens">{t("alert.weakens")}</h3>
            <ul className="reason-list">
              {groups.weakens.map((rc) => (
                <ReasonItem key={rc.code} rc={rc} alert={alert} highlight={highlight} onHighlight={onHighlight} tone="weakens" />
              ))}
            </ul>
          </>
        )}
        <p className="ctx__note">
          {t("alert.families")}: {alert.risk.supported_families.map((x) => tDynamic("family.", x)).join(", ") || "—"}.{" "}
          {alert.risk.missing_families.length > 0 && t("alert.missingFamilies", { list: alert.risk.missing_families.map((x) => tDynamic("family.", x)).join(", ") })}
        </p>
      </section>

      <section className="ctx__section">
        <h3 className="ctx__label ctx__label--unknown">{t("alert.unknown")}</h3>
        <ul className="reason-list" data-testid="limitations">
          {groups.unknown.map((rc) => (
            <ReasonItem key={rc.code} rc={rc} alert={alert} highlight={highlight} onHighlight={onHighlight} tone="unknown" />
          ))}
          {limitations.map((l) => (
            <li key={l} className="reason reason--unknown">
              <span className="reason__mark" aria-hidden="true">
                <Icon name="info" size={14} />
              </span>
              <div className="reason__body">{tDynamic("lim.", l)}</div>
            </li>
          ))}
        </ul>
        {alert.coverage.boundary_accounts.length > 0 && (
          <p className="ctx__note">
            {t("network.boundary")}:{" "}
            {alert.coverage.boundary_accounts.map((acc) => (
              <AccountId key={acc} id={acc} />
            ))}
          </p>
        )}
      </section>

      <section className="ctx__section" id="data-requests">
        <h3 className="ctx__label">{t("alert.next")}</h3>
        {requests.length === 0 ? (
          <p className="ctx__note">{t("alert.noDataRequests")}</p>
        ) : (
          <ol className="next-steps">
            {requests.map((r, i) => (
              <li key={`${r.type}-${i}`}>
                <strong>{tDynamic("nbdr.", r.type)}</strong>
                <span className="ctx__note">
                  {tDynamic("nbdr.res.", r.expected_resolution)} · {t("nbdr.subjects", { count: r.subject_ids.length })}
                  {r.proposed_window && ` · ${t("nbdr.window", { from: formatDate(r.proposed_window[0]!), to: formatDate(r.proposed_window[1]!) })}`}
                </span>
              </li>
            ))}
          </ol>
        )}
        <p className="ctx__note">{t("alert.dataRequestsHint")}</p>
      </section>

      <details className="disclosure disclosure--flat">
        <summary>
          <Icon name="chevronRight" size={16} className="disclosure__chevron" />
          <span>{t("alert.participants", { count: roles.size })}</span>
        </summary>
        <ul className="participants">
          {[...roles.entries()].map(([id, role]) => (
            <li key={id}>
              <button type="button" className="participant" onClick={() => onSelectAccount(id)}>
                <span className={`role-dot role-dot--${role}`} aria-hidden="true" />
                <code className="mono">{id}</code>
                <span className="participant__role">{t(ROLE_KEY[role])}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function BackToSummary({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" className="link-btn ctx__back" onClick={onBack}>
      <Icon name="arrowLeft" size={16} />
      {t("ctx.back")}
    </button>
  );
}

/** Reasons that cite any of the given transactions — the evidence references of a selection. */
function citingReasons(alert: AlertDetail, txIds: readonly string[]): { ev: EvidenceItem; text: string }[] {
  const set = new Set(txIds);
  return alert.evidence
    .filter((e) => e.transaction_ids.some((id) => set.has(id)))
    .map((ev) => {
      const rc = alert.risk.reason_codes.find((r) => r.code === ev.reason_code);
      return { ev, text: rc ? reasonText(rc as ReasonCode, alert.formation.currency) : tDynamic("evkind.", ev.kind, ev.reason_code) };
    });
}

export function AccountView({ alert, id, role, txs, onBack }: { alert: AlertDetail; id: string; role: NodeRole | undefined; txs: Transaction[]; onBack: () => void }) {
  const snapId = alert.snapshot.id;
  const summary = useApi(`acc:${snapId}:${id}`, (s) => api.get<AccountSummary>(`/api/v1/snapshots/${snapId}/accounts/${encodeURIComponent(id)}`, undefined, s));
  const flows = accountFlows(id, txs);
  const cur = alert.formation.currency;
  const refs = citingReasons(alert, flows.related.map((x) => x.id));
  return (
    <div className="ctx" data-testid="ctx-account">
      <BackToSummary onBack={onBack} />
      <section className="ctx__section">
        <span className="ctx__eyebrow">
          {role && <span className={`role-dot role-dot--${role}`} aria-hidden="true" />}
          {role ? t(ROLE_KEY[role]) : t("common.account")}
        </span>
        <h2 className="ctx__title ctx__title--id">
          <AccountId id={id} link={false} />
        </h2>
      </section>
      <section className="ctx__section">
        <h3 className="ctx__label">{t("ctx.inFormation")}</h3>
        <div className="flow-pair">
          <div className="flow-pair__item">
            <span className="flow-pair__label">{t("network.in")}</span>
            <strong className="num">{flows.mixedCurrency ? "—" : formatMoney(flows.inSum, cur)}</strong>
            <span className="cell-note">{t("alerts.transactions", { count: flows.inCount })}</span>
          </div>
          <div className="flow-pair__item">
            <span className="flow-pair__label">{t("network.out")}</span>
            <strong className="num">{flows.mixedCurrency ? "—" : formatMoney(flows.outSum, cur)}</strong>
            <span className="cell-note">{t("alerts.transactions", { count: flows.outCount })}</span>
          </div>
        </div>
      </section>
      <section className="ctx__section">
        <h3 className="ctx__label">{t("ctx.inSnapshot")}</h3>
        {summary.loading && !summary.data && <Loading rows={2} />}
        {summary.error && <ErrorState error={summary.error} onRetry={summary.reload} />}
        {summary.data && (
          <dl className="kv kv--compact">
            <dt>{t("network.in")}</dt>
            <dd>
              <Money minor={summary.data.incoming_minor} currency={cur} /> <span className="cell-note">· {t("network.counterparties", { count: summary.data.distinct_senders })}</span>
            </dd>
            <dt>{t("network.out")}</dt>
            <dd>
              <Money minor={summary.data.outgoing_minor} currency={cur} /> <span className="cell-note">· {t("network.counterparties", { count: summary.data.distinct_receivers })}</span>
            </dd>
            <dt>{t("network.formations")}</dt>
            <dd className="num">{summary.data.formations.length}</dd>
          </dl>
        )}
      </section>
      <section className="ctx__section">
        <h3 className="ctx__label">{t("ctx.transfers", { count: flows.related.length })}</h3>
        <ul className="mini-tx">
          {flows.related.slice(0, 8).map((tx) => {
            const out = tx.sender_account_id === id;
            const other = out ? tx.receiver_account_id : tx.sender_account_id;
            return (
              <li key={tx.id}>
                <span className={`mini-tx__dir mini-tx__dir--${out ? "out" : "in"}`} title={out ? t("network.out") : t("network.in")}>
                  <Icon name={out ? "arrowRight" : "arrowLeft"} size={14} />
                </span>
                <code className="mono mini-tx__cp" title={other}>
                  {shortId(other, 5)}
                </code>
                <span className="mini-tx__date num">{formatEventTime(tx.observed_date, tx.occurred_at)}</span>
                <Money minor={tx.amount_minor} currency={tx.currency} />
              </li>
            );
          })}
        </ul>
        {flows.related.length > 8 && <p className="ctx__note">{t("ctx.moreInTable", { count: flows.related.length - 8 })}</p>}
      </section>
      {refs.length > 0 && (
        <section className="ctx__section">
          <h3 className="ctx__label">{t("ctx.citedBy")}</h3>
          <ul className="cite-list">
            {refs.map((r) => (
              <li key={r.ev.id}>{r.text}</li>
            ))}
          </ul>
        </section>
      )}
      <Link className="btn btn--sm" to={`/network?account=${encodeURIComponent(id)}`}>
        <Icon name="network" size={16} />
        {t("ctx.openNetwork")}
      </Link>
    </div>
  );
}

export function EdgeView({ alert, edge, txs, onBack }: { alert: AlertDetail; edge: GraphEdgeSpec; txs: Transaction[]; onBack: () => void }) {
  const ids = new Set(edge.txIds ?? []);
  const rows = txs.filter((x) => ids.has(x.id));
  const refs = citingReasons(alert, [...ids]);
  return (
    <div className="ctx" data-testid="ctx-edge">
      <BackToSummary onBack={onBack} />
      <section className="ctx__section">
        <span className="ctx__eyebrow">{t("ctx.edge")}</span>
        <h2 className="ctx__title ctx__title--pair">
          <AccountId id={edge.source} compact />
          <Icon name="arrowRight" size={16} />
          <AccountId id={edge.target} compact />
        </h2>
        <div className="flow-pair">
          <div className="flow-pair__item">
            <span className="flow-pair__label">{t("ctx.edgeTotal")}</span>
            <strong className="num">
              <Money minor={edge.amountMinor} currency={edge.currency} />
            </strong>
          </div>
          <div className="flow-pair__item">
            <span className="flow-pair__label">{t("ctx.edgeCount")}</span>
            <strong className="num">{edge.count}</strong>
          </div>
        </div>
      </section>
      <section className="ctx__section">
        <h3 className="ctx__label">{t("ctx.transfers", { count: rows.length })}</h3>
        <ul className="tx-cards">
          {rows.map((tx) => (
            <li key={tx.id} className="tx-card">
              <div className="tx-card__amount">
                <Money minor={tx.amount_minor} currency={tx.currency} />
                <span className="cell-note">{tx.currency}</span>
              </div>
              <dl className="kv kv--compact">
                <dt>{t("common.from")}</dt>
                <dd>
                  <AccountId id={tx.sender_account_id} />
                </dd>
                <dt>{t("common.to")}</dt>
                <dd>
                  <AccountId id={tx.receiver_account_id} />
                </dd>
                <dt>{t("common.date")}</dt>
                <dd>
                  {formatEventTime(tx.observed_date, tx.occurred_at)}
                  {tx.time_precision === "day" && <span className="cell-note"> · {t("common.precisionDay")}</span>}
                </dd>
                <dt>{t("common.txId")}</dt>
                <dd>
                  <code className="mono" title={tx.id}>
                    {tx.source_transaction_id}
                  </code>
                </dd>
              </dl>
            </li>
          ))}
        </ul>
      </section>
      {refs.length > 0 && (
        <section className="ctx__section">
          <h3 className="ctx__label">{t("ctx.citedBy")}</h3>
          <ul className="cite-list">
            {refs.map((r) => (
              <li key={r.ev.id}>{r.text}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
