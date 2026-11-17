import { useMemo, useState } from "react";
import { formatDate, formatMoney } from "../../lib/format";
import { t } from "../../lib/i18n";
import type { Transaction } from "../../lib/types";

type Dir = "in" | "out" | "other";
const DIRS: Dir[] = ["in", "out", "other"];
const COLOR: Record<Dir, string> = { in: "var(--g-entry)", out: "var(--g-exit)", other: "var(--accent)" };

interface Day {
  date: string;
  sum: Record<Dir, bigint>;
  count: Record<Dir, number>;
  highlighted: boolean;
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Bar height as a display-only ratio; exact sums are shown as text. */
function ratio(v: bigint, max: bigint): number {
  if (max === 0n) return 0;
  return Number((v * 10000n) / max) / 100;
}

/**
 * Sequence of evidence transfers by calendar day, split by direction relative to the central account.
 * With day-precision sources the order inside a day is unknown, so a day is one undivided column.
 */
export function EvidenceTimeline({
  txs,
  center,
  windowStart,
  windowEnd,
  highlight,
  compact = false,
}: {
  txs: Transaction[];
  center: string;
  windowStart: string;
  windowEnd: string;
  highlight?: ReadonlySet<string>;
  compact?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const currencies = new Set(txs.map((x) => x.currency));
  const currency = currencies.size === 1 ? [...currencies][0]! : null;
  const dayOnly = txs.length > 0 && txs.every((x) => x.time_precision === "day");

  const days = useMemo<Day[]>(() => {
    const byDate = new Map<string, Day>();
    let d = windowStart;
    for (let i = 0; d <= windowEnd && i < 400; i++, d = addDays(windowStart, i)) {
      byDate.set(d, { date: d, sum: { in: 0n, out: 0n, other: 0n }, count: { in: 0, out: 0, other: 0 }, highlighted: false });
    }
    for (const tx of txs) {
      let day = byDate.get(tx.observed_date);
      if (!day) {
        day = { date: tx.observed_date, sum: { in: 0n, out: 0n, other: 0n }, count: { in: 0, out: 0, other: 0 }, highlighted: false };
        byDate.set(tx.observed_date, day);
      }
      const dir: Dir = tx.receiver_account_id === center ? "in" : tx.sender_account_id === center ? "out" : "other";
      day.sum[dir] += BigInt(tx.amount_minor);
      day.count[dir] += 1;
      if (highlight?.has(tx.id)) day.highlighted = true;
    }
    return [...byDate.values()].sort((a, b) => (a.date < b.date ? -1 : 1));
  }, [txs, center, windowStart, windowEnd, highlight]);

  // Bars encode money when the formation has one currency; otherwise transfer counts.
  const value = (day: Day, dir: Dir): bigint => (currency ? day.sum[dir] : BigInt(day.count[dir]));
  const total = (day: Day) => DIRS.reduce((a, dir) => a + value(day, dir), 0n);
  const max = days.reduce((m, day) => (total(day) > m ? total(day) : m), 0n);
  const hasHighlight = (highlight?.size ?? 0) > 0;
  const present = DIRS.filter((dir) => days.some((day) => day.count[dir] > 0));
  const hd = hover !== null ? days[hover] : undefined;
  const fmt = (v: bigint) => (currency ? formatMoney(v, currency, { fraction: false }) : v.toString());

  return (
    <div className={compact ? "tl tl--compact" : "tl"}>
      {!compact && (
        <ul className="series-legend">
          {present.map((dir) => (
            <li key={dir}>
              <span className="legend-swatch legend-swatch--area" style={{ color: COLOR[dir] }} aria-hidden="true" />
              {t(`timeline.${dir}`)}
            </li>
          ))}
          <li className="series-legend__note">{currency ? t("timeline.byAmount") : t("timeline.byCount")}</li>
        </ul>
      )}
      <div className="tl__plot" aria-hidden="true" onPointerLeave={() => setHover(null)}>
        {days.map((day, i) => {
          const tot = total(day);
          return (
            <div
              key={day.date}
              className="tl__col"
              data-empty={tot === 0n ? "true" : undefined}
              data-dim={hasHighlight && !day.highlighted ? "true" : undefined}
              data-hl={hasHighlight && day.highlighted ? "true" : undefined}
              onPointerEnter={() => setHover(i)}
            >
              <div className="tl__stack" style={{ height: `${ratio(tot, max)}%` }}>
                {DIRS.map((dir) =>
                  value(day, dir) > 0n ? <span key={dir} className="tl__seg" style={{ flexGrow: ratio(value(day, dir), tot), background: COLOR[dir] }} /> : null,
                )}
              </div>
            </div>
          );
        })}
        {hd && hover !== null && !compact && (
          <div className="chart__tooltip tl__tooltip" style={{ left: `${((hover + 0.5) / days.length) * 100}%`, transform: hover > days.length / 2 ? "translateX(calc(-100% - 8px))" : "translateX(8px)" }}>
            <div className="chart__tooltip-title">{formatDate(hd.date)}</div>
            {DIRS.filter((dir) => hd.count[dir] > 0).map((dir) => (
              <div key={dir} className="chart__tooltip-row">
                <span className="legend-swatch legend-swatch--area" style={{ color: COLOR[dir] }} />
                <span>{t(`timeline.${dir}`)}</span>
                <strong className="num">
                  {currency ? formatMoney(hd.sum[dir], currency) : ""} · {t("alerts.transactions", { count: hd.count[dir] })}
                </strong>
              </div>
            ))}
            {DIRS.every((dir) => hd.count[dir] === 0) && <div className="chart__tooltip-row">{t("timeline.none")}</div>}
          </div>
        )}
      </div>
      <div className="tl__axis" aria-hidden="true">
        <span className="num">{formatDate(days[0]?.date ?? windowStart).slice(0, 5)}</span>
        {!compact && max > 0n && <span className="tl__max num">{t("timeline.max", { value: fmt(max) })}</span>}
        <span className="num">{formatDate(days[days.length - 1]?.date ?? windowEnd).slice(0, 5)}</span>
      </div>
      {!compact && dayOnly && <p className="tl__note">{t("timeline.dayOnly")}</p>}
      <div className="visually-hidden">
      <table>
        <caption>{t("timeline.caption")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("common.date")}</th>
            {DIRS.map((dir) => (
              <th key={dir} scope="col">
                {t(`timeline.${dir}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days
            .filter((day) => total(day) > 0n)
            .map((day) => (
              <tr key={day.date}>
                <th scope="row">{formatDate(day.date)}</th>
                {DIRS.map((dir) => (
                  <td key={dir}>{day.count[dir] ? `${currency ? formatMoney(day.sum[dir], currency) : ""} (${day.count[dir]})` : "—"}</td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
