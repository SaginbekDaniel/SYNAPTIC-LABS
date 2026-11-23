/// <reference lib="webworker" />
/**
 * Graph layout worker: runs the cose force layout (coseLayout.ts) off the main thread. It receives the
 * element ids, seed positions and node sizes only, and returns positions; it makes no network request.
 * It says "ready" once its module (with Cytoscape) has loaded, so the page never sends work to, or
 * terminates, a worker that is still loading.
 */
import { computeCoseLayout, type LayoutInput } from "./coseLayout";

declare const self: DedicatedWorkerGlobalScope;

export type LayoutRequest = { id: number; input: LayoutInput };
export type LayoutResponse =
  | { type: "ready" }
  | { type: "result"; id: number; positions: Float64Array }
  | { type: "error"; id: number; error: string };

const post = (m: LayoutResponse, transfer: Transferable[] = []) => self.postMessage(m, transfer);

self.onmessage = (event: MessageEvent<LayoutRequest>) => {
  const { id, input } = event.data;
  try {
    const positions = computeCoseLayout(input);
    post({ type: "result", id, positions }, [positions.buffer]);
  } catch (err) {
    post({ type: "error", id, error: err instanceof Error ? err.message : String(err) });
  }
};

post({ type: "ready" });
