/**
 * Inline stroke icons on a 24px grid (geometry after Lucide, ISC licence).
 * Decorative by default (aria-hidden); the accessible name always comes from adjacent text
 * or the control's aria-label — never from the icon alone.
 */
import type { ReactNode, SVGProps } from "react";

const PATHS = {
  overview: (
    <>
      <rect x="3" y="3" width="7.5" height="9" rx="2" />
      <rect x="13.5" y="3" width="7.5" height="5" rx="2" />
      <rect x="13.5" y="11" width="7.5" height="10" rx="2" />
      <rect x="3" y="15" width="7.5" height="6" rx="2" />
    </>
  ),
  queue: (
    <>
      <path d="M8 6h13M8 12h13M8 18h13" />
      <path d="m3 6 1 1 2-2M3 12l1 1 2-2M3 18l1 1 2-2" />
    </>
  ),
  cases: (
    <>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v2" />
      <path d="M3 7v11a2 2 0 0 0 2 2h6" />
      <circle cx="17" cy="16" r="3" />
      <path d="m21 20-1.8-1.8" />
    </>
  ),
  analytics: (
    <>
      <path d="M3 3v16a2 2 0 0 0 2 2h16" />
      <path d="M8 17v-5M13 17V8M18 17v-8" />
    </>
  ),
  lab: (
    <>
      <path d="M9 3h6M10 3v6.5L4.6 18.2A1.8 1.8 0 0 0 6.1 21h11.8a1.8 1.8 0 0 0 1.5-2.8L14 9.5V3" />
      <path d="M7.5 15h9" />
    </>
  ),
  network: (
    <>
      <circle cx="5" cy="6" r="2.2" />
      <circle cx="19" cy="6" r="2.2" />
      <circle cx="12" cy="18" r="2.2" />
      <path d="M7 7.2 10.6 16M17 7.2 13.4 16M7.2 6h9.6" />
    </>
  ),
  benchmark: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </>
  ),
  chevronRight: <path d="m9 6 6 6-6 6" />,
  chevronDown: <path d="m6 9 6 6 6-6" />,
  arrowLeft: <path d="M19 12H5M11 18l-6-6 6-6" />,
  arrowRight: <path d="M5 12h14M13 6l6 6-6 6" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>
  ),
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />,
  monitor: (
    <>
      <rect x="2.5" y="4" width="19" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </>
  ),
  close: <path d="M18 6 6 18M6 6l12 12" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  fit: <path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4" />,
  expand: <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />,
  collapse: <path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" />,
  more: (
    <>
      <circle cx="5" cy="12" r="1.2" />
      <circle cx="12" cy="12" r="1.2" />
      <circle cx="19" cy="12" r="1.2" />
    </>
  ),
  check: <path d="m5 12 4.5 4.5L19 7" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 16v-5M12 8h.01" />
    </>
  ),
  bandCritical: (
    <>
      <path d="M8.2 3h7.6L21 8.2v7.6L15.8 21H8.2L3 15.8V8.2Z" />
      <path d="M12 8v5M12 16h.01" />
    </>
  ),
  bandHigh: (
    <>
      <path d="M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </>
  ),
  bandMedium: (
    <>
      <path d="M12 3 21 12 12 21 3 12Z" />
      <path d="M12 9v3.5M12 15.5h.01" />
    </>
  ),
  bandLow: <circle cx="12" cy="12" r="8" />,
  bandUnresolved: (
    <>
      <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
      <path d="M9.6 9.5a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.1-2.4 3.6M12 17h.01" />
    </>
  ),
  supported: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  ambiguous: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8" />
    </>
  ),
  contradicted: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </>
  ),
  unavailable: <circle cx="12" cy="12" r="9" strokeDasharray="2.5 3" />,
  play: <path d="M7 4.5v15l12-7.5Z" />,
  sliders: <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4" />,
  external: <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />,
  database: (
    <>
      <ellipse cx="12" cy="5.5" rx="8" ry="2.8" />
      <path d="M4 5.5v13c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8v-13M4 12c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, ...rest }: { name: IconName; size?: number } & Omit<SVGProps<SVGSVGElement>, "name">) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
