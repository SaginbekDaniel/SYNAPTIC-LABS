/**
 * The one case the deck follows from problem to product: collection funnel ··7530 from the synthetic demo-v1
 * dataset (seed 2026). Accounts, dates, amounts and the peer figures are copied from the product's investigation
 * screen (docs/design/screenshots/after/investigation-1440-dark.webp), which is also shown on the product slide.
 * The merchant "twin" on the problem slide is an illustration of a legitimate network with the same shape.
 */
export type NodeKind = "in" | "hub" | "out" | "plain";
export interface GNode { id: string; x: number; y: number; kind: NodeKind; label: string }
export interface GEdge { from: string; to: string; day: number; amount: string }

/** Graph geometry is in a 760 × 520 box. */
export const FUNNEL_NODES: GNode[] = [
  { id: "1614", x: 130, y: 60, kind: "in", label: "··1614" },
  { id: "7584", x: 130, y: 160, kind: "in", label: "··7584" },
  { id: "1355", x: 130, y: 260, kind: "in", label: "··1355" },
  { id: "6780", x: 130, y: 360, kind: "in", label: "··6780" },
  { id: "8960", x: 130, y: 460, kind: "in", label: "··8960" },
  { id: "7530", x: 400, y: 260, kind: "hub", label: "··7530" },
  { id: "9459", x: 630, y: 170, kind: "out", label: "··9459" },
  { id: "0282", x: 630, y: 350, kind: "out", label: "··0282" },
];

export const FUNNEL_EDGES: GEdge[] = [
  { from: "7584", to: "7530", day: 12, amount: "305 868 ₸" },
  { from: "6780", to: "7530", day: 12, amount: "816 995 ₸" },
  { from: "8960", to: "7530", day: 13, amount: "408 553 ₸" },
  { from: "1614", to: "7530", day: 14, amount: "601 214 ₸" },
  { from: "1355", to: "7530", day: 14, amount: "888 503 ₸" },
  { from: "7530", to: "9459", day: 17, amount: "1 238 665 ₸" },
  { from: "7530", to: "0282", day: 17, amount: "1 238 665 ₸" },
];

/** Daily totals of the evidence transfers (₸, rounded to thousands for the bars). In = into ··7530, out = from it. */
export const FUNNEL_DAYS = [
  { day: 12, inK: 1123, outK: 0 },
  { day: 13, inK: 409, outK: 0 },
  { day: 14, inK: 1490, outK: 0 },
  { day: 15, inK: 0, outK: 0 },
  { day: 16, inK: 0, outK: 0 },
  { day: 17, inK: 0, outK: 2477 },
];

/** Product output for this case (investigation screen). */
export const FUNNEL_FACTS = {
  temporalShare: "81,9 %",
  lag: "3–5 дн.",
  peerShare: 54.9, // largest 3-day share of turnover, %
  peerMedian: 41.8,
  peerFence: 85.6, // Tukey fence Q3 + 1.5·IQR
  peerCohort: 77,
  priority: 55,
};

/** Legitimate twin: a merchant collecting card settlements and paying out. Same shape, illustrative. */
export const MERCHANT_NODES: GNode[] = [
  { id: "p1", x: 130, y: 60, kind: "in", label: "··2041" },
  { id: "p2", x: 130, y: 160, kind: "in", label: "··5517" },
  { id: "p3", x: 130, y: 260, kind: "in", label: "··0938" },
  { id: "p4", x: 130, y: 360, kind: "in", label: "··7702" },
  { id: "p5", x: 130, y: 460, kind: "in", label: "··3126" },
  { id: "m", x: 400, y: 260, kind: "hub", label: "··4418" },
  { id: "o1", x: 630, y: 170, kind: "out", label: "··6650" },
  { id: "o2", x: 630, y: 350, kind: "out", label: "··1873" },
];
export const MERCHANT_EDGES: GEdge[] = [
  { from: "p1", to: "m", day: 12, amount: "" },
  { from: "p2", to: "m", day: 12, amount: "" },
  { from: "p3", to: "m", day: 13, amount: "" },
  { from: "p4", to: "m", day: 14, amount: "" },
  { from: "p5", to: "m", day: 14, amount: "" },
  { from: "m", to: "o1", day: 17, amount: "" },
  { from: "m", to: "o2", day: 17, amount: "" },
];
