import type { ReactNode } from "react";

/**
 * Circular progress for an explicit ratio. With no valid denominator it renders an empty
 * dashed track and "—" — a percentage is never shown without a source.
 */
export function Ring({
  value,
  total,
  label,
  detail,
  color = "var(--accent)",
  size = 92,
}: {
  value: number;
  total: number;
  label: string;
  detail: ReactNode;
  color?: string;
  size?: number;
}) {
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const valid = total > 0;
  const frac = valid ? Math.min(1, Math.max(0, value / total)) : 0;
  const pct = valid ? Math.round(frac * 100) : null;
  return (
    <figure className="ring">
      <div className="ring__figure" style={{ width: size, height: size }}>
        <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} strokeDasharray={valid ? undefined : "3 5"} />
          {valid && frac > 0 && (
            <circle
              className="ring__arc"
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={color}
              strokeWidth={stroke}
              strokeLinecap="round"
              strokeDasharray={`${c * frac} ${c}`}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            />
          )}
        </svg>
        <span className="ring__value num">{pct === null ? "—" : `${pct}%`}</span>
      </div>
      <figcaption>
        <span className="ring__label">{label}</span>
        <span className="ring__detail">{detail}</span>
      </figcaption>
    </figure>
  );
}

/** Segmented horizontal meter, e.g. a 0–100 queue priority. Exposed as role="meter" with the exact value. */
export function SegmentedMeter({
  value,
  max,
  segments = 10,
  label,
  valueText,
  tone = "accent",
}: {
  value: number | null;
  max: number;
  segments?: number;
  label: string;
  valueText: string;
  tone?: string;
}) {
  const filled = value === null ? 0 : Math.round((Math.min(max, Math.max(0, value)) / max) * segments);
  return (
    <div
      className={`meter meter--${tone}`}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value ?? undefined}
      aria-valuetext={valueText}
    >
      {Array.from({ length: segments }, (_, i) => (
        <span key={i} className="meter__seg" data-on={i < filled ? "true" : undefined} />
      ))}
    </div>
  );
}

export interface BarRow {
  key: string;
  label: ReactNode;
  value: number;
  /** Pre-formatted value text (units included). */
  display: string;
  color?: string;
  /** Optional reference marker on the same scale (e.g. previous version). */
  reference?: { value: number; label: string };
  note?: ReactNode;
}

/** Horizontal bars on one shared, labelled scale. Values are printed, so bars are never the only carrier. */
export function BarList({ rows, max, scaleLabel }: { rows: BarRow[]; max: number; scaleLabel?: string }) {
  const m = max > 0 ? max : 1;
  return (
    <div className="barlist">
      {scaleLabel && <div className="barlist__scale">{scaleLabel}</div>}
      <ul>
        {rows.map((r) => (
          <li key={r.key} className="barlist__row">
            <div className="barlist__label">
              {r.label}
              {r.note && <span className="barlist__note">{r.note}</span>}
            </div>
            <div className="barlist__track" aria-hidden="true">
              <span className="barlist__bar" style={{ width: `${(Math.max(0, r.value) / m) * 100}%`, background: r.color ?? "var(--accent)" }} />
              {r.reference && <span className="barlist__ref" style={{ left: `${(r.reference.value / m) * 100}%` }} title={r.reference.label} />}
            </div>
            <div className="barlist__value num">
              {r.display}
              {r.reference && <span className="barlist__refval">{r.reference.label}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Vertical columns for a handful of categories (counts). */
export function ColumnChart({ columns, label }: { columns: { key: string; label: string; value: number; color?: string }[]; label: string }) {
  const max = Math.max(1, ...columns.map((c) => c.value));
  return (
    <figure className="columns" aria-label={label}>
      <ul className="columns__plot">
        {columns.map((c) => (
          <li key={c.key} className="columns__col">
            <span className="columns__area">
              <span className="columns__value num">{c.value}</span>
              <span className="columns__bar" style={{ height: `${(c.value / max) * 100}%`, background: c.color ?? "var(--accent)" }} />
            </span>
            <span className="columns__label">{c.label}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
