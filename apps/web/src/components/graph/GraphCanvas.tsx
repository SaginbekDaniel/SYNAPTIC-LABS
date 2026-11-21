import cytoscape, { type Core, type ElementDefinition, type StylesheetJson } from "cytoscape";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useTheme } from "../../app/theme";
import { formatMoney, parseMinor } from "../../lib/format";
import { t, tDynamic, type MessageKey } from "../../lib/i18n";
import type { Band } from "../../lib/types";
import { Icon } from "../ui/icons";
import { toCanvasColor } from "./canvasColor";
import { GraphController, type GraphViewport } from "./controller";

export type NodeRole = "subject" | "entry" | "exit" | "member" | "boundary" | "context";
export type EdgeStatus = "supported" | "possible_ambiguous" | "contradicted" | "unavailable" | "mixed";

export interface GraphNodeSpec {
  id: string;
  role: NodeRole;
  /** Fixed position ("preset" layout) or deterministic seed ("cose" layout). */
  position?: { x: number; y: number };
  /** Stored risk band of the account's strongest formation (colorBy="band" only). */
  band?: Band | null;
  /** The account is the centre of at least one formation: drawn as a diamond. */
  hub?: boolean;
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
  /** Cited by formation evidence (investigation-graph edges). */
  evidence?: boolean;
  /** Temporal status of the formations the edge evidences; null = context transfer. */
  status?: EdgeStatus | null;
}

function cssToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** A colour token, converted to a notation Cytoscape's canvas parser accepts (see canvasColor.ts). */
function cssColor(name: string): string {
  return toCanvasColor(cssToken(name) || "#888");
}

function readPalette() {
  return {
    node: cssColor("--g-node"),
    subject: cssColor("--g-subject"),
    entry: cssColor("--g-entry"),
    exit: cssColor("--g-exit"),
    boundary: cssColor("--g-boundary"),
    edge: cssColor("--g-edge"),
    edgeStrong: cssColor("--g-edge-strong"),
    highlight: cssColor("--g-highlight"),
    label: cssColor("--g-label"),
    labelBg: cssColor("--g-label-bg"),
    stage: cssColor("--stage"),
    font: cssToken("--font-sans") || "sans-serif",
    critical: cssColor("--band-critical"),
    high: cssColor("--band-high"),
    medium: cssColor("--band-medium"),
    low: cssColor("--band-low"),
    unresolved: cssColor("--band-unresolved"),
    supported: cssColor("--ev-supported"),
    ambiguous: cssColor("--ev-ambiguous"),
    contradicted: cssColor("--ev-contradicted"),
    unavailable: cssColor("--ev-unavailable"),
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

type ColorBy = "role" | "band";

function stylesheet(p: Palette, colorBy: ColorBy): StylesheetJson {
  const roleColor = (role: NodeRole) =>
    ({ subject: p.subject, entry: p.entry, exit: p.exit, member: p.node, boundary: p.boundary, context: p.node })[role];
  const bandColor = (band: string | undefined) =>
    ({ critical: p.critical, high: p.high, medium: p.medium, low: p.low, insufficient_evidence: p.unresolved })[band ?? ""] ?? p.node;
  const fill = (ele: cytoscape.NodeSingular) =>
    colorBy === "band" ? bandColor(ele.data("band") as string | undefined) : roleColor(ele.data("role") as NodeRole);
  return [
    {
      selector: "node",
      style: {
        "background-color": fill,
        label: "data(label)",
        color: p.label,
        "font-family": p.font,
        "font-size": 11,
        "font-weight": 500,
        // Label density follows zoom: labels whose rendered size would be unreadable are not drawn.
        "min-zoomed-font-size": 7,
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
    { selector: "node[?hub]", style: { shape: "diamond", width: 26, height: 26 } },
    {
      selector: 'node[role = "subject"]',
      style: {
        width: 30,
        height: 30,
        "font-size": 12,
        "font-weight": 600,
        "underlay-color": colorBy === "band" ? p.highlight : p.subject,
        "underlay-padding": 9,
        "underlay-opacity": 0.22,
        "underlay-shape": "ellipse",
      },
    },
    { selector: "node.context", style: { opacity: 0.6, width: 12, height: 12 } },
    { selector: 'node[role = "boundary"]', style: { "border-style": "dashed", "border-color": p.boundary, "border-width": 2.5, "background-opacity": 0.35 } },
    { selector: "node.hover", style: { "underlay-color": p.highlight, "underlay-padding": 7, "underlay-opacity": 0.22, "underlay-shape": "ellipse", "min-zoomed-font-size": 0, "z-index": 9 } },
    { selector: "node.kbd", style: { "border-color": p.highlight, "border-width": 3, "min-zoomed-font-size": 0 } },
    {
      selector: "node.sel",
      style: { "border-color": p.edgeStrong, "border-width": 3, "underlay-color": p.highlight, "underlay-padding": 10, "underlay-opacity": 0.3, "underlay-shape": "ellipse", "min-zoomed-font-size": 0 },
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
        "min-zoomed-font-size": 7,
        color: p.label,
        "text-rotation": "autorotate",
        "text-background-color": p.labelBg,
        "text-background-opacity": 0.9,
        "text-background-padding": "2px",
        "transition-property": "line-color, target-arrow-color, opacity",
        "transition-duration": 160,
      },
    },
    // Evidence edges: the formations' temporal status decides the line, never motion. Contradicted
    // chronology is drawn dotted and is never presented as a proven money trail.
    { selector: 'edge[status = "supported"]', style: { "line-color": p.supported, "target-arrow-color": p.supported } },
    { selector: 'edge[status = "possible_ambiguous"]', style: { "line-color": p.ambiguous, "target-arrow-color": p.ambiguous, "line-style": "dashed", "line-dash-pattern": [7, 4] } },
    { selector: 'edge[status = "contradicted"]', style: { "line-color": p.contradicted, "target-arrow-color": p.contradicted, "line-style": "dotted" } },
    { selector: 'edge[status = "unavailable"]', style: { "line-color": p.unavailable, "target-arrow-color": p.unavailable, "line-style": "dashed", "line-dash-pattern": [2, 5] } },
    { selector: 'edge[status = "mixed"]', style: { "line-color": p.highlight, "target-arrow-color": p.highlight } },
    { selector: "edge.hl", style: { "line-color": p.highlight, "target-arrow-color": p.highlight, "z-index": 5 } },
    { selector: "edge.sel", style: { "line-color": p.edgeStrong, "target-arrow-color": p.edgeStrong, "z-index": 6, label: "data(amount)", "min-zoomed-font-size": 0 } },
    { selector: ".dim", style: { opacity: 0.16 } },
  ] as unknown as StylesheetJson;
}

/** Cytoscape behind the GraphController port. */
function cytoscapeViewport(cy: Core): GraphViewport {
  const node = (id: string) => {
    const n = cy.getElementById(id);
    return n.nonempty() && n.isNode() ? n : null;
  };
  return {
    size: () => ({ width: cy.width(), height: cy.height() }),
    zoom: () => cy.zoom(),
    zoomTo: (level, anchor) => cy.zoom({ level, renderedPosition: anchor }),
    panBy: (d) => cy.panBy(d),
    fit: () => cy.fit(undefined, 48),
    nodePosition: (id) => node(id)?.renderedPosition() ?? null,
    moveNode: (id, r) => node(id)?.renderedPosition({ x: r.x, y: r.y } as Record<string, number>),
    modelPosition: (id) => {
      const p = node(id)?.position();
      return p ? { x: p.x, y: p.y } : null;
    },
    setModelPosition: (id, p) => node(id)?.position({ x: p.x, y: p.y }),
    nodeIds: () => cy.nodes().map((n) => n.id()),
    centerOn: (id) => {
      const n = node(id);
      if (n) cy.animate({ center: { eles: n } }, { duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 200 });
    },
  };
}

export interface GraphCanvasProps {
  nodes: GraphNodeSpec[];
  edges: GraphEdgeSpec[];
  selectedNode?: string | null;
  selectedEdge?: string | null;
  /** Edge ids drawn as highlighted evidence. */
  highlightEdges?: ReadonlySet<string>;
  /** Node ids to keep at full strength while everything else is dimmed (e.g. one formation). */
  emphasis?: ReadonlySet<string> | null;
  layout?: "cose" | "preset";
  /** "role": formation roles (investigation). "band": stored risk band (graph workspace). */
  colorBy?: ColorBy;
  /** Show aggregated amounts on edges when the graph is small enough to stay legible. */
  edgeLabels?: boolean;
  /** Keyboard order for "next/previous account" ([ and ]). Defaults to the node order. */
  order?: string[];
  onSelectNode?: (id: string | null) => void;
  onSelectEdge?: (edge: GraphEdgeSpec | null) => void;
  onExpand?: (id: string) => void;
  /** Receives the controller once the canvas exists, and null when it is torn down. */
  onController?: (controller: GraphController | null) => void;
  /** Overlaid in the bottom-left corner of the stage (legend). */
  overlay?: ReactNode;
  /** Extra toolbar buttons (e.g. camera gestures). */
  controls?: ReactNode;
  /** Absolutely positioned layers inside the stage (e.g. a gesture pointer). */
  children?: ReactNode;
  className?: string;
  /** Accessible name for the stage; defaults to a node/edge count. */
  label?: string;
}

const MAX_EDGE_LABELS = 14;

/**
 * Cytoscape canvas. The graph is built once per element set; selection, highlight and theme are
 * applied as classes/styles on the live instance so interaction never re-runs layout.
 */
export function GraphCanvas(props: GraphCanvasProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const controllerRef = useRef<GraphController | null>(null);
  const { resolved } = useTheme();
  const [focus, setFocus] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [announce, setAnnounce] = useState("");
  const hintId = useId();
  const colorBy: ColorBy = props.colorBy ?? "role";
  const handlers = useRef(props);
  handlers.current = props;

  const labelEdges = (props.edgeLabels ?? true) && props.edges.length <= MAX_EDGE_LABELS;
  const elements = useMemo<ElementDefinition[]>(
    () => [
      ...props.nodes.map((n) => ({
        data: { id: n.id, label: shortLabel(n.id), role: n.role, band: n.band ?? undefined, hub: n.hub ? true : undefined },
        position: n.position ? { ...n.position } : undefined,
        classes: n.role === "context" ? "context" : "",
      })),
      ...props.edges.map((e) => {
        const amount = formatMoney(e.amountMinor, e.currency, { fraction: false });
        return {
          data: {
            id: e.id,
            source: e.source,
            target: e.target,
            width: edgeWidth(e.amountMinor),
            amount,
            label: labelEdges ? amount : "",
            status: e.status ?? undefined,
          },
        };
      }),
    ],
    [props.nodes, props.edges, labelEdges],
  );

  // Build (and destroy) the instance only when the element set, layout or colour mode changes.
  useEffect(() => {
    if (!ref.current) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cy = cytoscape({
      container: ref.current,
      elements,
      style: stylesheet(readPalette(), colorBy),
      wheelSensitivity: 0.25,
      minZoom: 0.15,
      maxZoom: 3,
      boxSelectionEnabled: false,
      layout: { name: "preset", fit: props.layout !== "cose", padding: 48 },
    });
    // The force layout is owned here so it can be stopped before destroy(): destroying an instance
    // while a layout is still iterating makes Cytoscape dereference its torn-down renderer.
    const layout =
      props.layout === "cose"
        ? cy.layout({
            name: "cose",
            // Positions are seeded per node id (see graphModel.seedPosition); with randomize off
            // and no coincident nodes, cose never consults Math.random → same input, same picture.
            randomize: false,
            // Settle off-screen, then move once to the result; no animation for reduced motion.
            animate: reduced ? false : "end",
            animationDuration: 260,
            nodeRepulsion: () => 9000,
            idealEdgeLength: () => 95,
            nodeOverlap: 12,
            numIter: 1000,
            padding: 36,
          } as cytoscape.LayoutOptions)
        : null;
    layout?.run();
    const controller = new GraphController(cytoscapeViewport(cy), {
      onSelectNode: (id) => handlers.current.onSelectNode?.(id),
      onSelectEdge: (id) => {
        const spec = id === null ? null : handlers.current.edges.find((e) => e.id === id) ?? null;
        handlers.current.onSelectEdge?.(spec);
      },
      onHover: (id) => {
        cy.nodes(".hover").removeClass("hover");
        if (id) cy.getElementById(id).addClass("hover");
      },
      onExpand: (id) => handlers.current.onExpand?.(id),
    });
    cy.on("tap", "node", (evt) => controller.dispatch({ type: "selectNode", id: evt.target.id() }));
    cy.on("tap", "edge", (evt) => controller.dispatch({ type: "selectEdge", id: evt.target.id() }));
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        controller.dispatch({ type: "selectNode", id: null });
        controller.dispatch({ type: "selectEdge", id: null });
      }
    });
    cy.on("dbltap", "node", (evt) => controller.dispatch({ type: "focusNode", id: evt.target.id() }));
    cy.on("mouseover", "node", (evt) => {
      evt.target.addClass("hover");
      if (ref.current) ref.current.style.cursor = "pointer";
    });
    cy.on("mouseover", "edge", () => ref.current && (ref.current.style.cursor = "pointer"));
    cy.on("mouseout", "node", (evt) => evt.target.removeClass("hover"));
    cy.on("mouseout", "node, edge", () => ref.current && (ref.current.style.cursor = ""));
    cyRef.current = cy;
    controllerRef.current = controller;
    handlers.current.onController?.(controller);
    return () => {
      handlers.current.onController?.(null);
      controllerRef.current = null;
      layout?.stop();
      cy.stop(true, false);
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements, props.layout, colorBy]);

  // Theme: restyle in place.
  useEffect(() => {
    cyRef.current?.style(stylesheet(readPalette(), colorBy));
  }, [resolved, colorBy]);

  // Selection, emphasis & highlight: classes only.
  const { selectedNode, selectedEdge, highlightEdges, emphasis } = props;
  const flagged = useMemo(() => new Set(props.edges.filter((e) => e.highlighted).map((e) => e.id)), [props.edges]);
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().removeClass("sel dim hl kbd");
      cy.edges().forEach((e) => {
        if (highlightEdges?.has(e.id()) || flagged.has(e.id())) e.addClass("hl");
      });
      if (cursor) cy.getElementById(cursor).addClass("kbd");
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
      } else if (emphasis && emphasis.size) {
        const nodes = cy.nodes().filter((n) => emphasis.has(n.id()));
        focusSet = nodes.union(nodes.edgesWith(nodes));
      }
      if (focusSet) cy.elements().difference(focusSet).addClass("dim");
    });
  }, [selectedNode, selectedEdge, highlightEdges, emphasis, flagged, elements, cursor]);

  // Focus mode: the stage fills the viewport; Escape leaves it.
  useEffect(() => {
    const cy = cyRef.current;
    if (cy) {
      cy.resize();
      cy.fit(undefined, 48);
    }
    if (!focus) return;
    const onKey = (e: globalThis.KeyboardEvent) => e.key === "Escape" && setFocus(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [focus]);

  const order = props.order ?? props.nodes.map((n) => n.id);
  const describe = (id: string) => {
    const n = props.nodes.find((x) => x.id === id);
    const band = n?.band ? tDynamic("band.", n.band) : t("graph.kbd.noBand");
    return t("graph.kbd.node", { id, band });
  };
  const moveCursor = (step: 1 | -1) => {
    const c = controllerRef.current;
    if (!c || order.length === 0) return;
    const i = cursor ? order.indexOf(cursor) : -1;
    const next = order[(i + step + order.length) % order.length];
    if (next === undefined) return;
    setCursor(next);
    c.dispatch({ type: "focusNode", id: next });
    setAnnounce(describe(next));
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const c = controllerRef.current;
    if (!c || e.altKey || e.ctrlKey || e.metaKey) return;
    const step = e.shiftKey ? 160 : 60;
    const keys: Record<string, () => void> = {
      ArrowLeft: () => c.dispatch({ type: "pan", dx: step, dy: 0 }),
      ArrowRight: () => c.dispatch({ type: "pan", dx: -step, dy: 0 }),
      ArrowUp: () => c.dispatch({ type: "pan", dx: 0, dy: step }),
      ArrowDown: () => c.dispatch({ type: "pan", dx: 0, dy: -step }),
      "+": () => c.dispatch({ type: "zoomStep", direction: 1 }),
      "=": () => c.dispatch({ type: "zoomStep", direction: 1 }),
      "-": () => c.dispatch({ type: "zoomStep", direction: -1 }),
      "0": () => c.dispatch({ type: "resetView" }),
      "]": () => moveCursor(1),
      "[": () => moveCursor(-1),
      Enter: () => cursor && c.dispatch({ type: "selectNode", id: cursor }),
      e: () => {
        const target = cursor ?? props.selectedNode;
        if (target && props.onExpand) c.dispatch({ type: "expandNeighborhood", id: target });
      },
      Escape: () => {
        c.dispatch({ type: "cancel" });
        setCursor(null);
      },
    };
    const run = keys[e.key];
    if (run) {
      e.preventDefault();
      run();
    }
  };

  return (
    <div className={`graph-stage${focus ? " graph-stage--focus" : ""}${props.className ? ` ${props.className}` : ""}`}>
      <div
        ref={ref}
        className="graph-stage__canvas"
        role="application"
        aria-roledescription={t("graph.roledescription")}
        aria-label={props.label ?? t("graph.alt", { nodes: props.nodes.length, edges: props.edges.length })}
        aria-describedby={hintId}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onBlur={() => setCursor(null)}
        data-testid="graph-canvas"
      />
      <p id={hintId} className="visually-hidden">
        {props.onExpand ? t("graph.kbd.hintExpand") : t("graph.kbd.hint")}
      </p>
      <p className="visually-hidden" aria-live="polite">
        {announce}
      </p>
      <div className="graph-stage__controls" role="toolbar" aria-label={t("graph.controls")}>
        <button type="button" className="icon-btn" onClick={() => controllerRef.current?.dispatch({ type: "zoomStep", direction: 1 })} aria-label={t("graph.zoomIn")} title={t("graph.zoomIn")}>
          <Icon name="plus" />
        </button>
        <button type="button" className="icon-btn" onClick={() => controllerRef.current?.dispatch({ type: "zoomStep", direction: -1 })} aria-label={t("graph.zoomOut")} title={t("graph.zoomOut")}>
          <Icon name="minus" />
        </button>
        <button type="button" className="icon-btn" onClick={() => controllerRef.current?.dispatch({ type: "resetView" })} aria-label={t("graph.fit")} title={t("graph.fit")}>
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
        {props.controls}
      </div>
      {props.children}
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
