import cytoscape, { type Core, type ElementDefinition, type StylesheetJson } from "cytoscape";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTheme } from "../../app/theme";
import { formatMoney, parseMinor } from "../../lib/format";
import { t, type MessageKey } from "../../lib/i18n";
import { Icon } from "../ui/icons";

export type NodeRole = "subject" | "entry" | "exit" | "member" | "boundary" | "context";

export interface GraphNodeSpec {
  id: string;
  role: NodeRole;
  /** Fixed position (used with the "preset" layout). */
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
  /** Evidence transactions aggregated into this edge (formation graphs only). */
  txIds?: string[];
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

function readPalette() {
  return {
    node: cssVar("--g-node"),
    subject: cssVar("--g-subject"),
    entry: cssVar("--g-entry"),
    exit: cssVar("--g-exit"),
    boundary: cssVar("--g-boundary"),
    edge: cssVar("--g-edge"),
    edgeStrong: cssVar("--g-edge-strong"),
    highlight: cssVar("--g-highlight"),
    label: cssVar("--g-label"),
    labelBg: cssVar("--g-label-bg"),
    stage: cssVar("--stage"),
    glow: cssVar("--accent-glow"),
    font: cssVar("--font-sans"),
  };
}
type Palette = ReturnType<typeof readPalette>;

/**
 * Edge width encodes the aggregated amount on a clamped log scale.
 * BigInt → digit count keeps this display-only mapping exact-input-safe.
 */
function edgeWidth(amountMinor: string): number {
  const digits = parseMinor(amountMinor).toString().length;
  return Math.min(7, Math.max(1.4, (digits - 4) * 0.95));
}

function shortLabel(id: string): string {
  return id.length > 10 ? `··${id.slice(-4)}` : id;
}

function stylesheet(p: Palette): StylesheetJson {
  const roleColor = (role: NodeRole) =>
    ({ subject: p.subject, entry: p.entry, exit: p.exit, member: p.node, boundary: p.boundary, context: p.node })[role];
  return [
    {
      selector: "node",
      style: {
        "background-color": (ele: cytoscape.NodeSingular) => roleColor(ele.data("role") as NodeRole),
        label: "data(label)",
        color: p.label,
        "font-family": p.font,
        "font-size": 11,
        "font-weight": 500,
        "text-valign": "bottom",
        "text-margin-y": 6,
        "text-background-color": p.labelBg,
        "text-background-opacity": 0.75,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        width: 18,
        height: 18,
        "border-width": 3,
        "border-color": p.stage,
        "transition-property": "opacity, border-color, underlay-opacity",
        "transition-duration": 160,
      },
    },
    {
      selector: 'node[role = "subject"]',
      style: {
        width: 30,
        height: 30,
        "font-size": 12,
        "font-weight": 600,
        "underlay-color": p.subject,
        "underlay-padding": 9,
        "underlay-opacity": 0.22,
        "underlay-shape": "ellipse",
      },
    },
    { selector: "node.context", style: { opacity: 0.6, width: 12, height: 12 } },
    { selector: 'node[role = "boundary"]', style: { "border-style": "dashed", "border-color": p.boundary, "border-width": 2.5, "background-opacity": 0.35 } },
    {
      selector: "node.sel",
      style: { "border-color": p.edgeStrong, "border-width": 3, "underlay-color": p.highlight, "underlay-padding": 10, "underlay-opacity": 0.3, "underlay-shape": "ellipse" },
    },
    {
      selector: "edge",
      style: {
        width: "data(width)",
        "line-color": p.edge,
        "target-arrow-color": p.edge,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.95,
        "curve-style": "bezier",
        "control-point-step-size": 28,
        label: "data(label)",
        "font-family": p.font,
        "font-size": 10,
        color: p.label,
        "text-rotation": "autorotate",
        "text-background-color": p.labelBg,
        "text-background-opacity": 0.9,
        "text-background-padding": "2px",
        "transition-property": "line-color, target-arrow-color, opacity",
        "transition-duration": 160,
      },
    },
    { selector: "edge.hl", style: { "line-color": p.highlight, "target-arrow-color": p.highlight, "z-index": 5 } },
    { selector: "edge.sel", style: { "line-color": p.edgeStrong, "target-arrow-color": p.edgeStrong, "z-index": 6, label: "data(amount)" } },
    { selector: ".dim", style: { opacity: 0.18 } },
  ] as unknown as StylesheetJson;
}

export interface GraphCanvasProps {
  nodes: GraphNodeSpec[];
  edges: GraphEdgeSpec[];
  selectedNode?: string | null;
  selectedEdge?: string | null;
  /** Edge ids drawn as highlighted evidence. */
  highlightEdges?: ReadonlySet<string>;
  layout?: "cose" | "preset";
  /** Show aggregated amounts on edges when the graph is small enough to stay legible. */
  edgeLabels?: boolean;
  onSelectNode?: (id: string | null) => void;
  onSelectEdge?: (edge: GraphEdgeSpec | null) => void;
  /** Overlaid in the bottom-left corner of the stage (legend). */
  overlay?: ReactNode;
  className?: string;
}

const MAX_EDGE_LABELS = 14;

/**
 * Cytoscape canvas. The graph is built once per element set; selection, highlight and theme are
 * applied as classes/styles on the live instance so interaction never re-runs layout.
 */
export function GraphCanvas(props: GraphCanvasProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const { resolved } = useTheme();
  const [focus, setFocus] = useState(false);
  const handlers = useRef({ onSelectNode: props.onSelectNode, onSelectEdge: props.onSelectEdge, edges: props.edges });
  handlers.current = { onSelectNode: props.onSelectNode, onSelectEdge: props.onSelectEdge, edges: props.edges };

  const labelEdges = (props.edgeLabels ?? true) && props.edges.length <= MAX_EDGE_LABELS;
  const elements = useMemo<ElementDefinition[]>(
    () => [
      ...props.nodes.map((n) => ({
        data: { id: n.id, label: shortLabel(n.id), role: n.role },
        position: n.position ? { ...n.position } : undefined,
        classes: n.role === "context" ? "context" : "",
      })),
      ...props.edges.map((e) => {
        const amount = formatMoney(e.amountMinor, e.currency, { fraction: false });
        return {
          data: { id: e.id, source: e.source, target: e.target, width: edgeWidth(e.amountMinor), amount, label: labelEdges ? amount : "" },
        };
      }),
    ],
    [props.nodes, props.edges, labelEdges],
  );

  // Build (and destroy) the instance only when the element set or layout changes.
  useEffect(() => {
    if (!ref.current) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cy = cytoscape({
      container: ref.current,
      elements,
      style: stylesheet(readPalette()),
      wheelSensitivity: 0.25,
      minZoom: 0.15,
      maxZoom: 3,
      boxSelectionEnabled: false,
      layout:
        props.layout === "cose"
          ? { name: "cose", animate: !reduced, animationDuration: 260, randomize: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 95, padding: 36 }
          : { name: "preset", fit: true, padding: 48 },
    });
    cy.on("tap", "node", (evt) => handlers.current.onSelectNode?.(evt.target.id()));
    cy.on("tap", "edge", (evt) => {
      const spec = handlers.current.edges.find((e) => e.id === evt.target.id());
      if (spec) handlers.current.onSelectEdge?.(spec);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        handlers.current.onSelectNode?.(null);
        handlers.current.onSelectEdge?.(null);
      }
    });
    cy.on("mouseover", "node, edge", () => ref.current && (ref.current.style.cursor = "pointer"));
    cy.on("mouseout", "node, edge", () => ref.current && (ref.current.style.cursor = ""));
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements, props.layout]);

  // Theme: restyle in place.
  useEffect(() => {
    cyRef.current?.style(stylesheet(readPalette()));
  }, [resolved]);

  // Selection & highlight: classes only.
  const { selectedNode, selectedEdge, highlightEdges } = props;
  const flagged = useMemo(() => new Set(props.edges.filter((e) => e.highlighted).map((e) => e.id)), [props.edges]);
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().removeClass("sel dim hl");
      cy.edges().forEach((e) => {
        if (highlightEdges?.has(e.id()) || flagged.has(e.id())) e.addClass("hl");
      });
      let focusSet: cytoscape.CollectionReturnValue | null = null;
      if (selectedNode) {
        const n = cy.getElementById(selectedNode);
        if (n.nonempty()) {
          n.addClass("sel");
          focusSet = n.closedNeighborhood();
        }
      } else if (selectedEdge) {
        const e = cy.getElementById(selectedEdge);
        if (e.nonempty()) {
          e.addClass("sel");
          focusSet = e.union(e.connectedNodes());
        }
      }
      if (focusSet) cy.elements().difference(focusSet).addClass("dim");
    });
  }, [selectedNode, selectedEdge, highlightEdges, flagged, elements]);

  // Focus mode: the stage fills the viewport; Escape leaves it.
  useEffect(() => {
    const cy = cyRef.current;
    if (cy) {
      cy.resize();
      cy.fit(undefined, 48);
    }
    if (!focus) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setFocus(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [focus]);

  const zoom = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  return (
    <div className={`graph-stage${focus ? " graph-stage--focus" : ""}${props.className ? ` ${props.className}` : ""}`}>
      <div ref={ref} className="graph-stage__canvas" role="img" aria-label={t("graph.alt", { nodes: props.nodes.length, edges: props.edges.length })} />
      <div className="graph-stage__controls" role="toolbar" aria-label={t("graph.controls")}>
        <button type="button" className="icon-btn" onClick={() => zoom(1.25)} aria-label={t("graph.zoomIn")} title={t("graph.zoomIn")}>
          <Icon name="plus" />
        </button>
        <button type="button" className="icon-btn" onClick={() => zoom(0.8)} aria-label={t("graph.zoomOut")} title={t("graph.zoomOut")}>
          <Icon name="minus" />
        </button>
        <button type="button" className="icon-btn" onClick={() => cyRef.current?.fit(undefined, 48)} aria-label={t("graph.fit")} title={t("graph.fit")}>
          <Icon name="fit" />
        </button>
        <span className="graph-stage__sep" aria-hidden="true" />
        <button
          type="button"
          className="icon-btn"
          onClick={() => setFocus((v) => !v)}
          aria-pressed={focus}
          aria-label={focus ? t("graph.focusExit") : t("graph.focus")}
          title={focus ? t("graph.focusExit") : t("graph.focus")}
        >
          <Icon name={focus ? "collapse" : "expand"} />
        </button>
      </div>
      {props.overlay && <div className="graph-stage__overlay">{props.overlay}</div>}
    </div>
  );
}

const LEGEND: { role: NodeRole; key: MessageKey; varName: string }[] = [
  { role: "subject", key: "graph.legend.subject", varName: "var(--g-subject)" },
  { role: "entry", key: "graph.legend.entry", varName: "var(--g-entry)" },
  { role: "exit", key: "graph.legend.exit", varName: "var(--g-exit)" },
  { role: "member", key: "graph.legend.member", varName: "var(--g-node)" },
  { role: "boundary", key: "graph.legend.boundary", varName: "var(--g-boundary)" },
];

export function GraphLegend({ roles, highlighted }: { roles: NodeRole[]; highlighted?: boolean }) {
  return (
    <ul className="graph-legend">
      {LEGEND.filter((i) => roles.includes(i.role)).map((i) => (
        <li key={i.role}>
          <span className={`graph-legend__dot${i.role === "boundary" ? " graph-legend__dot--dashed" : ""}`} style={{ color: i.varName }} aria-hidden="true" />
          {t(i.key)}
        </li>
      ))}
      <li>
        <span className="graph-legend__edge" aria-hidden="true" />
        {t("graph.legend.edge")}
      </li>
      {highlighted && (
        <li>
          <span className="graph-legend__edge graph-legend__edge--hl" aria-hidden="true" />
          {t("graph.legend.highlight")}
        </li>
      )}
    </ul>
  );
}
