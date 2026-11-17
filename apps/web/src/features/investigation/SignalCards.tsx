import { EvidenceBadge, Money } from "../../components/ui";
import { formatBp, formatDate } from "../../lib/format";
import { precisionLabel, t, tDynamic } from "../../lib/i18n";
import type { EvidenceItem } from "../../lib/types";

/** Chronology & amount compatibility (max-flow). Facts only; interpretation lives in the reasons. */
export function TemporalCard({ ev, currency }: { ev: EvidenceItem; currency: string }) {
  const o = ev.observations as Record<string, unknown>;
  const lagDays = typeof o.lag_days_min === "number" ? t("temporal.lagDays", { min: Number(o.lag_days_min), max: Number(o.lag_days_max) }) : t("temporal.noLag");
  const lagSec = typeof o.lag_seconds_min === "number" ? t("temporal.lagSeconds", { min: Number(o.lag_seconds_min), max: Number(o.lag_seconds_max) }) : null;
  const share = Number(o.compatible_fraction_bp);
  return (
    <section className="signal" id="temporal" aria-labelledby="temporal-title">
      <header className="signal__head">
        <div>
          <h3 id="temporal-title">{t("alert.temporal")}</h3>
          <p className="signal__hint">{t("alert.temporalHint")}</p>
        </div>
        <EvidenceBadge status={String(o.status)} />
      </header>
      {Number.isFinite(share) && (
        <div className="signal__share">
          <div className="signal__share-bar" aria-hidden="true">
            <span style={{ width: `${Math.min(100, share / 100)}%` }} />
          </div>
          <span className="num">{t("temporal.shareLine", { share: formatBp(share) })}</span>
        </div>
      )}
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
        <dt>{t("temporal.lag")}</dt>
        <dd>{lagSec ?? lagDays}</dd>
        <dt>{t("temporal.uncertain")}</dt>
        <dd className="num">{String(o.uncertain_transition_count)}</dd>
        <dt>{t("temporal.precision")}</dt>
        <dd>{precisionLabel(String(o.time_precision))}</dd>
      </dl>
    </section>
  );
}

/** Turnover concentration vs an activity-matched cohort: a scale with the account, median and fence. */
export function PeerCard({ ev, currency }: { ev: EvidenceItem; currency: string }) {
  const o = ev.observations as Record<string, unknown>;
  const th = ev.thresholds as Record<string, unknown>;
  const status = String(o.status);
  const days = Number(th.window_days);
  const bp = (v: unknown) => (typeof v === "number" ? formatBp(v) : "—");
  const factor = Number(o.cohort_count_factor);
  const pos = (v: unknown) => (typeof v === "number" ? `${Math.min(100, Math.max(0, v / 100))}%` : null);
  const account = pos(o.burst_share_bp);
  const median = pos(o.cohort_median_bp);
  const fence = pos(o.fence_bp);
  return (
    <section className="signal" id="peer" aria-labelledby="peer-title">
      <header className="signal__head">
        <div>
          <h3 id="peer-title">{t("peer.title")}</h3>
          <p className="signal__hint">{t("peer.hint")}</p>
        </div>
        <EvidenceBadge status={status} label={tDynamic("peer.status.", status)} />
      </header>
      {account && (
        <div className="peer-scale" aria-hidden="true">
          <div className="peer-scale__track">
            {fence && <span className="peer-scale__zone" style={{ left: fence }} />}
            {median && <span className="peer-scale__mark peer-scale__mark--median" style={{ left: median }} />}
            {fence && <span className="peer-scale__mark peer-scale__mark--fence" style={{ left: fence }} />}
            <span className="peer-scale__dot" style={{ left: account }} />
          </div>
          <div className="peer-scale__legend">
            <span>
              <i className="peer-scale__key peer-scale__key--dot" />
              {t("peer.legend.account")}
            </span>
            <span>
              <i className="peer-scale__key peer-scale__key--median" />
              {t("peer.legend.median")}
            </span>
            <span>
              <i className="peer-scale__key peer-scale__key--fence" />
              {t("peer.legend.fence")}
            </span>
          </div>
        </div>
      )}
      <dl className="kv" data-testid="peer-facts">
        <dt>{t("peer.burst", { days })}</dt>
        <dd className="num">{bp(o.burst_share_bp)}</dd>
        <dt>{t("peer.median")}</dt>
        <dd className="num">{bp(o.cohort_median_bp)}</dd>
        <dt>{t("peer.fence")}</dt>
        <dd className="num">{bp(o.fence_bp)}</dd>
        <dt>{t("peer.cohort")}</dt>
        <dd>
          {t("peer.cohortSize", { count: Number(o.cohort_size) })}
          {Number.isFinite(factor) && <span className="cell-note"> · {factor === 0 ? t("peer.cohortAll") : t("peer.cohortFactor", { factor })}</span>}
        </dd>
        {typeof o.turnover_minor === "string" && (
          <>
            <dt>{t("peer.turnover")}</dt>
            <dd>
              <Money minor={o.turnover_minor} currency={currency} />
            </dd>
          </>
        )}
        {typeof o.window_start === "string" && (
          <>
            <dt>{t("peer.window")}</dt>
            <dd>{formatDate(o.window_start)}</dd>
          </>
        )}
      </dl>
    </section>
  );
}
