import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ApiError } from "../../lib/api";
import { formatEventTime, formatMoney, shortId } from "../../lib/format";
import { t, tDynamic } from "../../lib/i18n";
import type { Band, Transaction } from "../../lib/types";
import { Icon, type IconName } from "./icons";

export { Icon, type IconName } from "./icons";

/* ---------------------------------------------------------------- layout */

export function PageHeader(props: {
  title: ReactNode;
  description?: ReactNode;
  back?: { to: string; label: string };
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="page-head__text">
        {props.back && (
          <Link to={props.back.to} className="page-head__back">
            <Icon name="arrowLeft" size={16} />
            {props.back.label}
          </Link>
        )}
        <h1>{props.title}</h1>
        {props.description && <p className="page-head__desc">{props.description}</p>}
        {props.meta && <div className="page-head__meta">{props.meta}</div>}
      </div>
      {props.actions && <div className="page-head__actions">{props.actions}</div>}
    </header>
  );
}

export function Panel(props: {
  title?: ReactNode;
  actions?: ReactNode;
  flush?: boolean;
  children: ReactNode;
  id?: string;
  hint?: ReactNode;
  className?: string;
}) {
  const headingId = props.id ? `${props.id}-title` : undefined;
  return (
    <section className={props.className ? `panel ${props.className}` : "panel"} aria-labelledby={props.title ? headingId : undefined} id={props.id}>
      {(props.title || props.actions) && (
        <div className="panel__head">
          <div className="panel__titles">
            {props.title && <h2 id={headingId}>{props.title}</h2>}
            {props.hint && <p className="panel__hint">{props.hint}</p>}
          </div>
          {props.actions && <div className="panel__actions">{props.actions}</div>}
        </div>
      )}
      <div className={props.flush ? "panel__body panel__body--flush" : "panel__body"}>{props.children}</div>
    </section>
  );
}

/** Progressive disclosure for technical detail. Native <details>: keyboard and screen-reader support for free. */
export function Disclosure({ summary, children, defaultOpen = false, id }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean; id?: string }) {
  return (
    <details className="disclosure" open={defaultOpen} id={id}>
      <summary>
        <Icon name="chevronRight" size={16} className="disclosure__chevron" />
        <span>{summary}</span>
      </summary>
      <div className="disclosure__body">{children}</div>
    </details>
  );
}

export function Segmented<T extends string>(props: {
  label: string;
  value: T;
  options: { value: T; label: ReactNode; count?: number }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
}) {
  return (
    <div className={props.size === "sm" ? "segmented segmented--sm" : "segmented"} role="group" aria-label={props.label}>
      {props.options.map((o) => (
        <button
          key={o.value}
          type="button"
          className="segmented__item"
          aria-pressed={o.value === props.value}
          onClick={() => props.onChange(o.value)}
        >
          {o.label}
          {o.count !== undefined && <span className="segmented__count num">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- status */

const BAND_ICON: Record<Band, IconName> = {
  critical: "bandCritical",
  high: "bandHigh",
  medium: "bandMedium",
  low: "bandLow",
  insufficient_evidence: "bandUnresolved",
};

export function bandIcon(band: Band): IconName {
  return BAND_ICON[band] ?? "bandLow";
}

/** Risk band: colour + distinct icon shape + text, so meaning never depends on colour alone. */
export function BandBadge({ band, size = "md" }: { band: Band; size?: "sm" | "md" }) {
  return (
    <span className={`badge badge--${band}${size === "sm" ? " badge--sm" : ""}`}>
      <Icon name={bandIcon(band)} size={size === "sm" ? 12 : 14} />
      {t(`band.${band}`)}
    </span>
  );
}

const EV_ICON: Record<string, IconName> = {
  supported: "supported",
  possible_ambiguous: "ambiguous",
  contradicted: "contradicted",
  unavailable: "unavailable",
};

export function EvidenceBadge({ status, label }: { status: string | null | undefined; label?: string }) {
  if (!status) return null;
  return (
    <span className={`badge badge--${status}`}>
      <Icon name={EV_ICON[status] ?? "info"} size={14} />
      {label ?? tDynamic("ev.", status)}
    </span>
  );
}

const CASE_TONE: Record<string, string> = {
  new: "pending",
  investigating: "pending",
  reopened: "pending",
  escalated: "high",
  dismissed: "neutral",
  closed: "confirmed",
};

export function CaseStatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge--case badge--tone-${CASE_TONE[status] ?? "neutral"}`}>
      <span className="badge__dot" aria-hidden="true" />
      {tDynamic("cs.", status)}
    </span>
  );
}

export function SimulationBadge() {
  return (
    <span className="badge badge--sim" title={t("app.simulationHint")}>
      <Icon name="lab" size={14} />
      {t("app.simulation")}
    </span>
  );
}

/* ---------------------------------------------------------------- values */

export function Money({ minor, currency = "KZT" }: { minor: string; currency?: string }) {
  return (
    <span className="num" title={t("common.minorUnits", { minor })}>
      {formatMoney(minor, currency)}
    </span>
  );
}

/** Account identifiers are opaque strings: shown verbatim, never converted to numbers. */
export function AccountId({ id, link = true, compact = false }: { id: string; link?: boolean; compact?: boolean }) {
  const body = (
    <code className="mono account-id" title={compact ? id : undefined}>
      {compact ? shortId(id, 4) : id}
    </code>
  );
  if (!link) return body;
  return (
    <Link to={`/network?account=${encodeURIComponent(id)}`} title={t("network.openAccount", { id })} className="account-link">
      {body}
    </Link>
  );
}

/** Key figure with a definition. `value` is pre-formatted; numbers are never computed here. */
export function Stat(props: { label: string; value: ReactNode; hint?: ReactNode; to?: string; testId?: string; icon?: IconName; tone?: string }) {
  const body = (
    <>
      <div className="stat__label">
        {props.icon && (
          <span className={`stat__icon${props.tone ? ` stat__icon--${props.tone}` : ""}`}>
            <Icon name={props.icon} size={16} />
          </span>
        )}
        {props.label}
      </div>
      <div className="stat__value num">{props.value}</div>
      {props.hint && <div className="stat__hint">{props.hint}</div>}
    </>
  );
  return props.to ? (
    <Link to={props.to} className="stat stat--link" data-testid={props.testId}>
      {body}
    </Link>
  ) : (
    <div className="stat" data-testid={props.testId}>
      {body}
    </div>
  );
}

/* ---------------------------------------------------------------- states */

export function Loading({ rows = 4, label }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton-stack" role="status" aria-live="polite">
      <span className="visually-hidden">{label ?? t("state.loading")}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${92 - ((i * 13) % 40)}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="state state--error" role="alert">
      <span className="state__icon">
        <Icon name="contradicted" size={22} />
      </span>
      <strong>{error.code === "NETWORK_UNAVAILABLE" ? t("state.network") : t("state.error")}</strong>
      <span className="state__body">{error.message}</span>
      <span className="state__meta">{t("state.errorCode", { code: error.code, rid: error.requestId ?? "—" })}</span>
      {onRetry && (
        <button type="button" className="btn btn--sm" onClick={onRetry}>
          {t("state.retry")}
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children, icon = "info" }: { title: string; children?: ReactNode; icon?: IconName }) {
  return (
    <div className="state">
      <span className="state__icon">
        <Icon name={icon} size={22} />
      </span>
      <strong>{title}</strong>
      {children && <div className="state__body">{children}</div>}
    </div>
  );
}

export function NoDataset() {
  return (
    <Empty title={t("state.noDatasetTitle")} icon="database">
      <p>{t("state.noDatasetBody")}</p>
      <Link className="btn btn--primary" to="/lab">
        <Icon name="lab" size={16} />
        {t("state.toLab")}
      </Link>
    </Empty>
  );
}

/* ---------------------------------------------------------------- tables */

export function TxTable({
  rows,
  highlight,
  caption,
  limit = 12,
  selectedPair,
}: {
  rows: Transaction[];
  highlight?: ReadonlySet<string>;
  caption: string;
  limit?: number;
  /** Rows of this sender→receiver pair are marked as the current graph selection. */
  selectedPair?: { source: string; target: string } | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, limit);
  // State the time precision once when it is uniform; mark rows only in mixed tables.
  const allDay = rows.length > 0 && rows.every((r) => r.time_precision === "day");
  return (
    <div className="tx-table">
      <div className="table-wrap">
        <table className="table">
          <caption className="visually-hidden">{caption}</caption>
          <thead>
            <tr>
              <th scope="col">
                {t("common.date")}
                {allDay && <span className="th-note"> {t("common.precisionDayParen")}</span>}
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
              <tr
                key={tx.id}
                data-highlight={highlight?.has(tx.id) ? "true" : undefined}
                data-selected={selectedPair && tx.sender_account_id === selectedPair.source && tx.receiver_account_id === selectedPair.target ? "true" : undefined}
              >
                <td className="num">
                  {formatEventTime(tx.observed_date, tx.occurred_at)}
                  {!allDay && tx.time_precision === "day" && <div className="cell-note">{t("common.precisionDay")}</div>}
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
                  <code className="mono cell-note" title={`${tx.source_transaction_id} · ${tx.id}`}>
                    {shortId(tx.source_transaction_id, 6)}
                  </code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > limit && (
        <div className="tx-table__more">
          <button type="button" className="btn btn--sm btn--ghost" onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
            {expanded ? t("common.showLess") : t("common.showAll", { count: rows.length })}
          </button>
        </div>
      )}
    </div>
  );
}
