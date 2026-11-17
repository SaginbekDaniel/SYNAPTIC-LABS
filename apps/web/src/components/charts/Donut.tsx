import type { ReactNode } from "react";
import { t } from "../../lib/i18n";
import { Icon, type IconName } from "../ui/icons";

export interface DonutSegment {
  key: string;
  label: string;
  value: number;
  color: string;
  icon?: IconName;
}

const SIZE = 184;
const STROKE = 20;
const R = (SIZE - STROKE) / 2;
const C = 2 * Math.PI * R;
const GAP = 3; // px of track left between segments

function pctText(v: number, total: number): string {
  if (total === 0) return "—";
  return `${Math.round((v / total) * 100)} %`;
}

/**
 * Part-to-whole for ≤ 5 categories. Every slice is also listed with its count and share, so the
 * legend is the accessible representation; slices and legend rows share the same select action.
 */
export function Donut({
  segments,
  centerValue,
  centerLabel,
  label,
  selected,
  onSelect,
  footer,
}: {
  segments: DonutSegment[];
  centerValue: ReactNode;
  centerLabel: string;
  label: string;
  selected?: string | null;
  onSelect?: (key: string) => void;
  footer?: ReactNode;
}) {
  const total = segments.reduce((a, s) => a + s.value, 0);
  const visible = segments.filter((s) => s.value > 0);
  const gap = visible.length > 1 ? GAP : 0;
  let offset = 0;
  const arcs = visible.map((s) => {
    const len = (s.value / total) * C;
    const arc = { s, dash: `${Math.max(0.5, len - gap)} ${C}`, offset: -offset };
    offset += len;
    return arc;
  });
  return (
    <div className="donut">
      <div className="donut__figure">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width={SIZE} height={SIZE} role="img" aria-label={label}>
          <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="var(--surface-3)" strokeWidth={STROKE} />
          <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
            {arcs.map((a) => (
              <circle
                key={a.s.key}
                className="donut__arc"
                data-dim={selected && selected !== a.s.key ? "true" : undefined}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={R}
                fill="none"
                stroke={a.s.color}
                strokeWidth={STROKE}
                strokeDasharray={a.dash}
                strokeDashoffset={a.offset}
                strokeLinecap="butt"
                onClick={onSelect ? () => onSelect(a.s.key) : undefined}
              />
            ))}
          </g>
        </svg>
        <div className="donut__center" aria-hidden="true">
          <span className="donut__value num">{centerValue}</span>
          <span className="donut__label">{centerLabel}</span>
        </div>
      </div>
      <ul className="donut__legend">
        {segments.map((s) => {
          const body = (
            <>
              <span className="donut__key" style={{ color: s.color }}>
                {s.icon ? <Icon name={s.icon} size={15} /> : <span className="donut__dot" />}
              </span>
              <span className="donut__name">{s.label}</span>
              <span className="donut__count num">{s.value}</span>
              <span className="donut__pct num">{pctText(s.value, total)}</span>
            </>
          );
          return (
            <li key={s.key}>
              {onSelect ? (
                <button
                  type="button"
                  className="donut__row"
                  aria-pressed={selected === s.key}
                  onClick={() => onSelect(s.key)}
                  aria-label={t("chart.segment", { label: s.label, count: s.value, share: pctText(s.value, total) })}
                >
                  {body}
                </button>
              ) : (
                <div className="donut__row">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
      {footer}
    </div>
  );
}
