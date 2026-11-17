import { useEffect } from "react";
import { Link } from "react-router-dom";
import type { NodeRole } from "../../components/graph/GraphCanvas";
import { AccountId, BandBadge, CaseStatusBadge, ErrorState, EvidenceBadge, Icon, Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { reasonText, t } from "../../lib/i18n";
import type { AlertDetail, AlertSummary, EvidenceChain, ReasonCode } from "../../lib/types";
import { useApi } from "../../lib/useApi";
import { groupReasons, limitationsOf } from "../investigation/evidence";
import { EvidenceTimeline } from "../investigation/EvidenceTimeline";
import { buildFormationGraph, type FormationGraph } from "../investigation/formationGraph";
import { alertTitle } from "./alertText";

const ROLE_VAR: Record<NodeRole, string> = {
  subject: "var(--g-subject)",
  entry: "var(--g-entry)",
  exit: "var(--g-exit)",
  member: "var(--g-node)",
  boundary: "var(--g-boundary)",
  context: "var(--g-node)",
};

/** Static SVG of the formation, using the investigation layout. Decorative: the facts are in text. */
function NetworkMini({ graph }: { graph: FormationGraph }) {
  const pts = graph.nodes.map((n) => n.position ?? { x: 0, y: 0 });
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const pad = 30;
  const minX = Math.min(...xs) - pad;
  const minY = Math.min(...ys) - pad;
  const w = Math.max(...xs) - minX + pad;
  const h = Math.max(...ys) - minY + pad;
  const pos = new Map(graph.nodes.map((n, i) => [n.id, pts[i]!]));
  return (
    <svg className="mini-net" viewBox={`${minX} ${minY} ${w} ${h}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      {graph.edges.map((e) => {
        const a = pos.get(e.source);
        const b = pos.get(e.target);
        if (!a || !b) return null;
        return <line key={e.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="mini-net__edge" />;
      })}
      {graph.nodes.map((n) => {
        const p = pos.get(n.id)!;
        const r = n.role === "subject" ? 13 : 8;
        return (
          <g key={n.id}>
            {n.role === "subject" && <circle cx={p.x} cy={p.y} r={r + 9} fill={ROLE_VAR.subject} opacity={0.18} />}
            <circle cx={p.x} cy={p.y} r={r} fill={ROLE_VAR[n.role]} stroke="var(--surface-2)" strokeWidth={3} strokeDasharray={n.role === "boundary" ? "3 2" : undefined} />
          </g>
        );
      })}
    </svg>
  );
}

export function AlertPreview({ alert, onClose, onOpen }: { alert: AlertSummary; onClose: () => void; onOpen: () => void }) {
  const detail = useApi(`alert:${alert.id}`, (s) => api.get<AlertDetail>(`/api/v1/alerts/${alert.id}`, undefined, s));
  const chain = useApi(`chain:${alert.id}`, (s) => api.get<EvidenceChain>(`/api/v1/alerts/${alert.id}/evidence`, undefined, s));
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const d = detail.data;
  const graph = d && chain.data ? buildFormationGraph(d, chain.data.transactions, new Set()) : null;
  const groups = d ? groupReasons(d) : null;
  const limits = d ? limitationsOf(d).length + groups!.unknown.length : 0;
  const f = alert.formation;

  return (
    <aside className="panel queue__preview" aria-labelledby="preview-title" data-testid="alert-preview">
      <div className="preview__head">
        <div className="preview__badges">
          <BandBadge band={alert.risk.band} />
          <EvidenceBadge status={alert.temporal_status} />
          {alert.case_status && <CaseStatusBadge status={alert.case_status} />}
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label={t("common.close")}>
          <Icon name="close" />
        </button>
      </div>
      <h2 id="preview-title" className="preview__title">
        {alertTitle(alert)}
      </h2>
      <AccountId id={f.subject_account_id} />
      <button type="button" className="btn btn--primary btn--block" onClick={onOpen} data-testid="open-investigation">
        {t("preview.open")}
        <Icon name="arrowRight" size={16} />
      </button>

      <div className="preview__net">
        {graph ? <NetworkMini graph={graph} /> : chain.error ? <ErrorState error={chain.error} onRetry={chain.reload} /> : <div className="skeleton skeleton--block" />}
        <span className="preview__net-note num">
          {t("alerts.accounts", { count: f.member_count })} · {t("alerts.transactions", { count: alert.transaction_count })}
        </span>
      </div>

      {detail.error && <ErrorState error={detail.error} onRetry={detail.reload} />}
      {!d && !detail.error && <Loading rows={4} />}
      {d && groups && (
        <>
          <section className="preview__section">
            <h3 className="ctx__label ctx__label--supports">{t("alert.supports")}</h3>
            <ul className="reason-list reason-list--compact">
              {groups.supports.map((rc) => (
                <li key={rc.code} className="reason reason--supports">
                  <span className="reason__mark" aria-hidden="true">
                    <Icon name="check" size={14} />
                  </span>
                  <div className="reason__body">{reasonText(rc as ReasonCode, f.currency)}</div>
                </li>
              ))}
            </ul>
            {groups.weakens.length > 0 && (
              <>
                <h3 className="ctx__label ctx__label--weakens">{t("alert.weakens")}</h3>
                <ul className="reason-list reason-list--compact">
                  {groups.weakens.map((rc) => (
                    <li key={rc.code} className="reason reason--weakens">
                      <span className="reason__mark" aria-hidden="true">
                        <Icon name="minus" size={14} />
                      </span>
                      <div className="reason__body">{reasonText(rc as ReasonCode, f.currency)}</div>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {limits > 0 && <p className="ctx__note">{t("preview.limits", { count: limits })}</p>}
          </section>
          {chain.data && (
            <section className="preview__section">
              <h3 className="ctx__label">
                {t("timeline.title")}{" "}
                <span className="cell-note num">
                  {formatDate(f.window_start)} — {formatDate(f.window_end)}
                </span>
              </h3>
              <EvidenceTimeline compact txs={chain.data.transactions} center={f.subject_account_id} windowStart={f.window_start} windowEnd={f.window_end} />
            </section>
          )}
        </>
      )}
      <div className="preview__actions">
        <Link className="link-btn" to={`/network?account=${encodeURIComponent(f.subject_account_id)}`}>
          <Icon name="network" size={16} />
          {t("ctx.openNetwork")}
        </Link>
      </div>
    </aside>
  );
}
