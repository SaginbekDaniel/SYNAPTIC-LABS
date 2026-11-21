/**
 * Cytoscape draws on a canvas with its own colour parser, which understands hex, names and the
 * legacy comma forms `rgb(r, g, b)` / `rgba(r, g, b, a)` only. The design tokens use CSS Color 4
 * notation (`rgb(163 167 200 / 0.38)`), which Cytoscape rejects as an invalid style value — the
 * element then silently falls back to Cytoscape's default grey. Every token that enters the graph
 * stylesheet goes through this conversion, so tokens can keep the modern notation.
 */
const RGB = /^rgba?\(\s*([\d.]+%?)\s*[,\s]\s*([\d.]+%?)\s*[,\s]\s*([\d.]+%?)\s*(?:[,/]\s*([\d.]+%?)\s*)?\)$/i;

const channel = (v: string) => Math.round(Math.min(255, Math.max(0, v.endsWith("%") ? (parseFloat(v) * 255) / 100 : parseFloat(v))));
const alpha = (v: string) => Math.min(1, Math.max(0, v.endsWith("%") ? parseFloat(v) / 100 : parseFloat(v)));

export function toCanvasColor(value: string): string {
  const m = RGB.exec(value.trim());
  if (!m) return value.trim();
  const [r, g, b] = [m[1]!, m[2]!, m[3]!].map(channel);
  return m[4] === undefined ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${alpha(m[4])})`;
}
