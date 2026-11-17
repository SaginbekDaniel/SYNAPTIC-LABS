import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";
import { formatMoney, parseMinor } from "../../lib/format";
import { t } from "../../lib/i18n";

export type NodeRole = "subject" | "entry" | "exit" | "member" | "boundary" | "context";

export interface GraphNodeSpec {
  id: string;
  role: NodeRole;
  /** Optional fixed position (used with the "preset" layout). */
  position?: { x: number; y: number };
}

export interface GraphEdgeSpec {
  id: string;
  source: string;
  target: string;
  amountMinor: string;
  currency: string;
  count: number;
  highlighted?: boolean;
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

function usePalette() {
  const [scheme, setScheme] = useState(0);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setScheme((n) => n + 1);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return useMemo(
    () => ({
      node: cssVar("--g-node"),
      subject: cssVar("--g-subject"),
      entry: cssVar("--g-entry"),
      exit: cssVar("--g-exit"),
      boundary: cssVar("--g-boundary"),
      edge: cssVar("--g-edge"),
      edgeStrong: cssVar("--g-edge-strong"),
      text: cssVar("--text"),
      textMuted: cssVar("--text-2"),
      accent: cssVar("--accent"),
      surface: cssVar("--surface"),
    }),
    [scheme],
  );
}

/**
 * Edge width encodes the documented aggregated amount on a clamped log scale.
 * BigInt → digit count keeps this display-only mapping exact-input-safe.
 */
function edgeWidth(amountMinor: string): number {
  const digits = parseMinor(amountMinor).toString().length;
  return Math.min(7, Math.max(1.2, (digits - 4) * 0.9));
}

const MAX_EDGE_LABELS = 12;

function shortLabel(id: string): string {
  return id.length > 12 ? `…${id.slice(-6)}` : id;
}

export function GraphCanvas(props: {
  nodes: GraphNodeSpec[];
  edges: GraphEdgeSpec[];
  selectedNode?: string | null;
  layout?: "breadthfirst" | "cose" | "preset";
  tall?: boolean;
  onSelectNode?: (id: string) => void;
  onSelectEdge?: (edge: GraphEdgeSpec) => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const palette = usePalette();
  const { onSelectNode, onSelectEdge } = props;
  const handlers = useRef({ onSelectNode, onSelectEdge });
  handlers.current = { onSelectNode, onSelectEdge };

  useEffect(() => {
    if (!ref.current) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const roleColor: Record<NodeRole, string> = {
      subject: palette.subject,
      entry: palette.entry,
      exit: palette.exit,
      member: palette.node,
      boundary: palette.boundary,
      context: palette.node,
    };
    const elements: ElementDefinition[] = [
      ...props.nodes.map((n) => ({
        data: { id: n.id, label: shortLabel(n.id), color: roleColor[n.role], role: n.role },
        position: n.position ? { ...n.position } : undefined,
        classes: n.role === "context" ? "context" : n.role === "boundary" ? "boundary" : "",
      })),
      ...props.edges.map((e) => ({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          width: edgeWidth(e.amountMinor),
          // Amount labels only while the graph stays legible; the table always carries exact values.
          label: props.layout !== "preset" && props.edges.length <= MAX_EDGE_LABELS ? formatMoney(e.amountMinor, e.currency, { fraction: false }) : "",
        },
        classes: e.highlighted ? "hl" : "",
      })),
    ];
    const cy = cytoscape({
      container: ref.current,
      elements,
      wheelSensitivity: 0.2,
      minZoom: 0.2,
      maxZoom: 3,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: palette.text,
            "font-size": 10,
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: 18,
            height: 18,
            "border-width": 2,
            "border-color": palette.surface,
          },
        },
        { selector: "node.context", style: { opacity: 0.55, width: 12, height: 12 } },
        { selector: "node.boundary", style: { "border-style": "dashed", "border-color": palette.boundary, "border-width": 3 } },
        { selector: "node:selected", style: { "border-color": palette.accent, "border-width": 4 } },
        {
          selector: "edge",
          style: {
            width: "data(width)",
            "line-color": palette.edge,
            "target-arrow-color": palette.edge,
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.9,
            label: "data(label)",
            "font-size": 8,
            color: palette.textMuted,
            "text-rotation": "autorotate",
            "text-background-color": palette.surface,
            "text-background-opacity": 0.85,
            "text-background-padding": "1px",
          },
        },
        { selector: "edge.hl", style: { "line-color": palette.accent, "target-arrow-color": palette.accent } },
        { selector: "edge:selected", style: { "line-color": palette.edgeStrong, "target-arrow-color": palette.edgeStrong } },
      ],
      layout:
        props.layout === "cose"
          ? { name: "cose", animate: false, randomize: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, padding: 24 }
          : props.layout === "preset"
            ? { name: "preset", fit: true, padding: 32 }
            : { name: "breadthfirst", directed: true, spacingFactor: 1.15, animate: !reduced, animationDuration: 200, padding: 24 },
    });
    cy.on("tap", "node", (evt) => handlers.current.onSelectNode?.(evt.target.id()));
    cy.on("tap", "edge", (evt) => {
      const spec = props.edges.find((e) => e.id === evt.target.id());
      if (spec) handlers.current.onSelectEdge?.(spec);
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [props.nodes, props.edges, props.layout, palette]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().unselect();
    if (props.selectedNode) cy.getElementById(props.selectedNode).select();
  }, [props.selectedNode]);

  return (
    <div
      ref={ref}
      className={props.tall ? "graph graph--tall" : "graph"}
      role="img"
      aria-label={t("graph.alt", { nodes: props.nodes.length, edges: props.edges.length })}
    />
  );
}

export function GraphLegend({ roles }: { roles: NodeRole[] }) {
  const items: { role: NodeRole; key: Parameters<typeof t>[0]; varName: string }[] = [
    { role: "subject", key: "graph.legend.subject", varName: "var(--g-subject)" },
    { role: "entry", key: "graph.legend.entry", varName: "var(--g-entry)" },
    { role: "exit", key: "graph.legend.exit", varName: "var(--g-exit)" },
    { role: "member", key: "graph.legend.member", varName: "var(--g-node)" },
    { role: "boundary", key: "graph.legend.boundary", varName: "var(--g-boundary)" },
  ];
  return (
    <div className="legend">
      {items
        .filter((i) => roles.includes(i.role))
        .map((i) => (
          <span key={i.role}>
            <span className="legend__dot" style={{ background: i.varName }} aria-hidden="true" />
            {t(i.key)}
          </span>
        ))}
    </div>
  );
}
