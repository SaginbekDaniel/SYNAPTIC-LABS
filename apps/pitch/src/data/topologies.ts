import type { EdgeSpec, NodeSpec, Tone } from "../ui/Network";

/** Shared node/edge universe for the intelligence-engine graph (740 x 440 viewBox). */
export type TopoId = "funnel" | "fanout" | "chain" | "cycle";
export const GRAPH_W = 740;
export const GRAPH_H = 440;

type Pt = [number, number];
const POS: Record<TopoId, Record<string, Pt>> = {
  funnel: {
    f1: [70, 50], f2: [70, 140], f3: [70, 220], f4: [70, 300], f5: [70, 390], h: [370, 220],
    o1: [670, 140], o2: [670, 300], o3: [370, 220], o4: [370, 220], o5: [370, 220], o6: [370, 220],
  },
  fanout: {
    f1: [70, 140], f2: [70, 300], h: [300, 220], f3: [300, 220], f4: [300, 220], f5: [300, 220],
    o1: [670, 30], o2: [670, 112], o3: [670, 194], o4: [670, 276], o5: [670, 358], o6: [670, 420],
  },
  chain: {
    f1: [60, 360], f2: [215, 110], h: [370, 360], o1: [525, 110], o2: [680, 360],
    f3: [370, 220], f4: [370, 220], f5: [370, 220], o3: [370, 220], o4: [370, 220], o5: [370, 220], o6: [370, 220],
  },
  cycle: {
    f1: [370, 60], f2: [545, 190], h: [480, 360], o1: [260, 360], o2: [195, 190],
    f3: [370, 220], f4: [370, 220], f5: [370, 220], o3: [370, 220], o4: [370, 220], o5: [370, 220], o6: [370, 220],
  },
};

const VISIBLE: Record<TopoId, string[]> = {
  funnel: ["f1", "f2", "f3", "f4", "f5", "h", "o1", "o2"],
  fanout: ["f1", "f2", "h", "o1", "o2", "o3", "o4", "o5", "o6"],
  chain: ["f1", "f2", "h", "o1", "o2"],
  cycle: ["f1", "f2", "h", "o1", "o2"],
};

const ALL_NODES = ["f1", "f2", "f3", "f4", "f5", "h", "o1", "o2", "o3", "o4", "o5", "o6"];

type EdgeDef = [string, string, string]; // id, from, to
const EDGES: Record<TopoId, EdgeDef[]> = {
  funnel: [
    ["f1h", "f1", "h"], ["f2h", "f2", "h"], ["f3h", "f3", "h"], ["f4h", "f4", "h"], ["f5h", "f5", "h"],
    ["ho1", "h", "o1"], ["ho2", "h", "o2"],
  ],
  fanout: [
    ["f1h", "f1", "h"], ["f2h", "f2", "h"],
    ["ho1", "h", "o1"], ["ho2", "h", "o2"], ["ho3", "h", "o3"], ["ho4", "h", "o4"], ["ho5", "h", "o5"], ["ho6", "h", "o6"],
  ],
  chain: [["c1", "f1", "f2"], ["c2", "f2", "h"], ["c3", "h", "o1"], ["c4", "o1", "o2"]],
  cycle: [["c1", "f1", "f2"], ["c2", "f2", "h"], ["c3", "h", "o1"], ["c4", "o1", "o2"], ["c5", "o2", "f1"]],
};
const ALL_EDGE_IDS = [
  "f1h", "f2h", "f3h", "f4h", "f5h", "ho1", "ho2", "ho3", "ho4", "ho5", "ho6", "c1", "c2", "c3", "c4", "c5",
];

export interface TopoStyle {
  tone?: (id: string) => Tone;
  edgeTone?: (id: string) => Tone;
  flow?: boolean;
  labels?: Record<string, string>;
  edgeLabels?: Record<string, string>;
  selectable?: (id: string) => (() => void) | undefined;
  hubPulse?: boolean;
}

const defaultTone = (id: string): Tone =>
  id === "h" ? "hub" : id.startsWith("f") ? "source" : "sink";

export function buildTopology(topo: TopoId, s: TopoStyle = {}): { nodes: NodeSpec[]; edges: EdgeSpec[] } {
  const visible = new Set(VISIBLE[topo]);
  const nodes: NodeSpec[] = ALL_NODES.map((id) => {
    const [x, y] = POS[topo][id];
    return {
      id, x, y,
      hidden: !visible.has(id),
      tone: (s.tone ?? defaultTone)(id),
      r: id === "h" ? 20 : 13,
      label: s.labels?.[id],
      pulse: id === "h" && s.hubPulse,
    };
  });
  const defs = new Map(EDGES[topo].map((d) => [d[0], d]));
  const edges: EdgeSpec[] = ALL_EDGE_IDS.map((id) => {
    const d = defs.get(id);
    return d
      ? { id, from: d[1], to: d[2], tone: (s.edgeTone ?? (() => "neutral" as Tone))(id), flow: s.flow ?? true, label: s.edgeLabels?.[id], onSelect: s.selectable?.(id) }
      : { id, from: "h", to: "h", hidden: true };
  });
  return { nodes, edges };
}
