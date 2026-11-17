import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ApiError } from "../../lib/api";
import { formatEventTime, formatMoney, shortId } from "../../lib/format";
import { t, tDynamic } from "../../lib/i18n";
import type { Band, Transaction } from "../../lib/types";

export function Panel(props: { title?: ReactNode; actions?: ReactNode; flush?: boolean; children: ReactNode; id?: string; hint?: ReactNode }) {
  const headingId = props.id ? `${props.id}-title` : undefined;
  return (
    <section className="panel" aria-labelledby={headingId} id={props.id}>
      {(props.title || props.actions) && (
        <div className="panel__head">
          <div>
            {props.title && <h2 id={headingId}>{props.title}</h2>}
            {props.hint && <p className="subtle">{props.hint}</p>}
          </div>
          {props.actions && <div className="row">{props.actions}</div>}
        </div>
      )}
      <div className={props.flush ? "panel__body panel__body--flush" : "panel__body"}>{props.children}</div>
    </section>
  );
}

export function BandBadge({ band }: { band: Band }) {
  return <span className={`badge badge--${band}`}>{t(`band.${band}`)}</span>;
}

export function EvidenceBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null;
  return <span className={`badge badge--${status}`}>{tDynamic("ev.", status)}</span>;
}

export function CaseStatusBadge({ status }: { status: string }) {
  return <span className="badge badge--outline">{tDynamic("cs.", status)}</span>;
}

export function SimulationBadge() {
  return (
    <span className="badge badge--sim" title={t("app.simulationHint")}>
      {t("app.simulation")}
    </span>
  );
}

export function Money({ minor, currency = "KZT" }: { minor: string; currency?: string }) {
  return (
    <span className="num" title={`${minor} (minor units)`}>
      {formatMoney(minor, currency)}
    </span>
  );
}

/** Account identifiers are opaque strings: shown verbatim, never converted to numbers. */
export function AccountId({ id, link = true }: { id: string; link?: boolean }) {
  const body = <code className="mono">{id}</code>;
  if (!link) return body;
  return (
    <Link to={`/network?account=${encodeURIComponent(id)}`} title={t("nav.network")}>
      {body}
    </Link>
  );
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="stack stack--sm" role="status" aria-live="polite">
      <span className="visually-hidden">{t("state.loading")}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="state" role="alert">
      <strong>{error.code === "NETWORK_UNAVAILABLE" ? t("state.network") : t("state.error")}</strong>
      <span className="subtle">
        {error.message}
        <br />
        {t("state.errorCode", { code: error.code, rid: error.requestId ?? "—" })}
      </span>
      {onRetry && (
        <button type="button" className="btn btn--sm" onClick={onRetry}>
          {t("state.retry")}
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

export function NoDataset() {
  return (
    <Empty title={t("state.noDatasetTitle")}>
      <span>{t("state.noDatasetBody")}</span>
      <Link className="btn btn--primary" to="/lab">
        {t("state.toLab")}
      </Link>
    </Empty>
  );
}

export function TxTable({
  rows,
  highlight,
  caption,
  limit = 12,
}: {
  rows: Transaction[];
  highlight?: ReadonlySet<string>;
  caption: string;
  limit?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, limit);
  // State the time precision once when it is uniform; mark rows only in mixed tables.
  const allDay = rows.length > 0 && rows.every((r) => r.time_precision === "day");
  return (
    <div className="stack stack--sm">
      <div className="table-wrap">
        <table className="table">
          <caption className="visually-hidden">{caption}</caption>
          <thead>
            <tr>
              <th scope="col">
                {t("common.date")}
                {allDay && <span className="subtle"> · {t("common.precisionDay")}</span>}
              </th>
              <th scope="col" className="right">
                {t("common.amount")}
              </th>
              <th scope="col">{t("common.from")}</th>
              <th scope="col">{t("common.to")}</th>
              <th scope="col">{t("common.txId")}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((tx) => (
              <tr key={tx.id} data-highlight={highlight?.has(tx.id) ? "true" : undefined}>
                <td className="num">
                  {formatEventTime(tx.observed_date, tx.occurred_at)}
                  {!allDay && tx.time_precision === "day" && <div className="subtle">{t("common.precisionDay")}</div>}
                </td>
                <td className="right">
                  <Money minor={tx.amount_minor} currency={tx.currency} />
                </td>
                <td>
                  <AccountId id={tx.sender_account_id} />
                </td>
                <td>
                  <AccountId id={tx.receiver_account_id} />
                </td>
                <td className="id-cell">
                  <code className="mono subtle" title={`${tx.source_transaction_id} · ${tx.id}`}>
                    {shortId(tx.source_transaction_id, 6)}
                  </code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > limit && (
        <div>
          <button type="button" className="btn btn--sm btn--ghost" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
            {expanded ? t("common.showLess") : t("common.showAll", { count: rows.length })}
          </button>
        </div>
      )}
    </div>
  );
}
