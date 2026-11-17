import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { formatDate } from "../../lib/format";
import { t } from "../../lib/i18n";
import { monotonePath, niceStep, useElementWidth } from "./useElementWidth";

export interface ActivitySeries {
  key: string;
  label: string;
  /** CSS colour token, e.g. "var(--accent)". */
  color: string;
  kind: "area" | "line";
}

export interface ActivityPoint {
  date: string;
  values: Record<string, number>;
}

const M = { top: 16, right: 12, bottom: 28, left: 40 };

/**
 * Daily counts over calendar dates. Dates are day-precision, so the x axis never shows a clock time.
 * Keyboard: focus the chart and use ←/→ (Home/End) to read each day; a hidden table carries all values.
 */
export function ActivityChart({
  points,
  series,
  height = 260,
  caption,
  unit,
}: {
  points: ActivityPoint[];
  series: ActivitySeries[];
  height?: number;
  caption: string;
  unit: string;
}) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const gid = useId().replace(/:/g, "");

  const geo = useMemo(() => {
    const innerW = Math.max(0, width - M.left - M.right);
    const innerH = height - M.top - M.bottom;
    const peak = Math.max(1, ...points.flatMap((p) => series.map((s) => p.values[s.key] ?? 0)));
    const step = niceStep(peak);
    const max = Math.ceil(peak / step) * step;
    const x = (i: number) => M.left + (points.length <= 1 ? innerW / 2 : (innerW * i) / (points.length - 1));
    const y = (v: number) => M.top + innerH - (innerH * v) / max;
    const paths = series.map((s) => {
      const pts = points.map((p, i) => [x(i), y(p.values[s.key] ?? 0)] as [number, number]);
      const line = monotonePath(pts);
      const area = pts.length ? `${line}L${x(points.length - 1)},${y(0)}L${x(0)},${y(0)}Z` : "";
      return { s, line, area };
    });
    const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step);
    const every = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor(innerW / 84))));
    const xTicks = points.map((p, i) => ({ i, p })).filter(({ i }) => i % every === 0 || i === points.length - 1);
    return { innerW, innerH, x, y, paths, ticks, xTicks };
  }, [width, height, points, series]);

  function onKey(e: KeyboardEvent) {
    if (!points.length) return;
    const last = points.length - 1;
    const cur = active ?? -1;
    let next: number | null = null;
    if (e.key === "ArrowRight") next = Math.min(last, cur + 1);
    else if (e.key === "ArrowLeft") next = Math.max(0, cur < 0 ? last : cur - 1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else if (e.key === "Escape") setActive(null);
    if (next !== null) {
      e.preventDefault();
      setActive(next);
    }
  }

  function onPointer(clientX: number, rectLeft: number) {
    if (points.length === 0 || geo.innerW <= 0) return;
    const rel = (clientX - rectLeft - M.left) / geo.innerW;
    setActive(Math.max(0, Math.min(points.length - 1, Math.round(rel * (points.length - 1)))));
  }

  const ap = active !== null ? points[active] : undefined;
  const tipLeft = active !== null ? geo.x(active) : 0;
  const shortDate = (d: string) => formatDate(d).slice(0, 5);

  return (
    <div className="chart">
      <div
        ref={ref}
        className="chart__frame"
        tabIndex={0}
        role="img"
        aria-label={`${caption}. ${t("chart.keyboardHint")}`}
        onKeyDown={onKey}
        onPointerMove={(e) => onPointer(e.clientX, e.currentTarget.getBoundingClientRect().left)}
        onPointerLeave={() => setActive(null)}
        onBlur={() => setActive(null)}
        style={{ height }}
      >
        {width > 0 && (
          <svg width={width} height={height} aria-hidden="true">
            <defs>
              {geo.paths
                .filter((p) => p.s.kind === "area")
                .map((p) => (
                  <linearGradient key={p.s.key} id={`${gid}-${p.s.key}`} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor={p.s.color} stopOpacity={0.34} />
                    <stop offset="100%" stopColor={p.s.color} stopOpacity={0} />
                  </linearGradient>
                ))}
            </defs>
            {geo.ticks.map((v) => (
              <g key={v}>
                <line className="chart__grid" x1={M.left} x2={width - M.right} y1={geo.y(v)} y2={geo.y(v)} />
                <text className="chart__tick" x={M.left - 8} y={geo.y(v)} textAnchor="end" dominantBaseline="middle">
                  {v.toLocaleString("ru-RU")}
                </text>
              </g>
            ))}
            {geo.xTicks.map(({ i, p }) => (
              <text key={p.date} className="chart__tick" x={geo.x(i)} y={height - 8} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>
                {shortDate(p.date)}
              </text>
            ))}
            {geo.paths.map((p) =>
              p.s.kind === "area" ? (
                <g key={p.s.key}>
                  <path d={p.area} fill={`url(#${gid}-${p.s.key})`} />
                  <path d={p.line} fill="none" stroke={p.s.color} strokeWidth={2.25} strokeLinejoin="round" />
                </g>
              ) : (
                <path key={p.s.key} d={p.line} fill="none" stroke={p.s.color} strokeWidth={2} strokeDasharray="6 4" strokeLinejoin="round" />
              ),
            )}
            {ap && (
              <g>
                <line className="chart__cursor" x1={tipLeft} x2={tipLeft} y1={M.top} y2={M.top + geo.innerH} />
                {series.map((s) => (
                  <circle key={s.key} cx={tipLeft} cy={geo.y(ap.values[s.key] ?? 0)} r={4.5} fill="var(--surface)" stroke={s.color} strokeWidth={2.25} />
                ))}
              </g>
            )}
          </svg>
        )}
        {ap && (
          <div className="chart__tooltip" style={{ left: tipLeft, transform: `translateX(${tipLeft > width / 2 ? "calc(-100% - 12px)" : "12px"})` }}>
            <div className="chart__tooltip-title">{formatDate(ap.date)}</div>
            {series.map((s) => (
              <div key={s.key} className="chart__tooltip-row">
                <span className={`legend-swatch legend-swatch--${s.kind}`} style={{ color: s.color }} aria-hidden="true" />
                <span>{s.label}</span>
                <strong className="num">{(ap.values[s.key] ?? 0).toLocaleString("ru-RU")}</strong>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="visually-hidden" aria-live="polite">
        {ap ? `${formatDate(ap.date)}: ${series.map((s) => `${s.label} ${ap.values[s.key] ?? 0}`).join(", ")}` : ""}
      </div>
      <div className="visually-hidden">
      <table>
        <caption>
          {caption} ({unit})
        </caption>
        <thead>
          <tr>
            <th scope="col">{t("common.date")}</th>
            {series.map((s) => (
              <th key={s.key} scope="col">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date}>
              <th scope="row">{formatDate(p.date)}</th>
              {series.map((s) => (
                <td key={s.key}>{p.values[s.key] ?? 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}

export function SeriesLegend({ series }: { series: ActivitySeries[] }) {
  return (
    <ul className="series-legend">
      {series.map((s) => (
        <li key={s.key}>
          <span className={`legend-swatch legend-swatch--${s.kind}`} style={{ color: s.color }} aria-hidden="true" />
          {s.label}
        </li>
      ))}
    </ul>
  );
}
