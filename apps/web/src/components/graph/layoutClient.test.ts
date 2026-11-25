import { beforeEach, describe, expect, it } from "vitest";
import { seedPosition } from "../../features/graph/graphModel";
import { computeCoseLayout, type LayoutInput } from "./coseLayout";
import { cachedLayout, clearLayoutCache, LayoutCancelled, LayoutClient } from "./layoutClient";
import type { LayoutRequest, LayoutResponse } from "./layoutWorker";
import { layoutKey } from "./coseLayout";

function input(n: number, tag = "a"): LayoutInput {
  return {
    nodes: Array.from({ length: n }, (_, i) => ({ id: `${tag}${i}`, ...seedPosition(`${tag}${i}`), w: 24, h: 24 })),
    edges: Array.from({ length: n - 1 }, (_, i) => ({ source: `${tag}${i + 1}`, target: `${tag}${Math.floor(i / 2)}` })),
  };
}

/** A worker stand-in: records requests; the test answers them (or crashes it) explicitly. */
class FakeWorker {
  static created: FakeWorker[] = [];
  onmessage: ((e: MessageEvent<LayoutResponse>) => void) | null = null;
  onerror: ((e: ErrorEvent) => void) | null = null;
  requests: LayoutRequest[] = [];
  terminated = false;
  constructor() {
    FakeWorker.created.push(this);
  }
  postMessage(m: LayoutRequest) {
    this.requests.push(m);
  }
  terminate() {
    this.terminated = true;
  }
  ready() {
    this.onmessage?.({ data: { type: "ready" } } as MessageEvent<LayoutResponse>);
  }
  answer(i = this.requests.length - 1) {
    const r = this.requests[i]!;
    this.onmessage?.({ data: { type: "result", id: r.id, positions: computeCoseLayout(r.input) } } as MessageEvent<LayoutResponse>);
  }
  crash() {
    this.onerror?.({ preventDefault() {} } as ErrorEvent);
  }
}
const factory = () => new FakeWorker() as unknown as Worker;

describe("LayoutClient", () => {
  beforeEach(() => {
    clearLayoutCache();
    FakeWorker.created = [];
  });

  it("computes in the worker, caches the result, and answers a repeat from the cache without the worker", async () => {
    const client = new LayoutClient(factory);
    const job = client.layout(input(12));
    const worker = FakeWorker.created[0]!;
    expect(worker.requests).toHaveLength(0); // nothing is sent before the worker's module has loaded
    worker.ready();
    expect(worker.requests).toHaveLength(1);
    worker.answer();
    const positions = await job;
    expect(Array.from(positions)).toEqual(Array.from(computeCoseLayout(input(12))));
    expect(cachedLayout(layoutKey(input(12)))).toBe(positions);
    expect(await client.layout(input(12))).toBe(positions);
    expect(worker.requests).toHaveLength(1);
  });

  it("a new request supersedes a computing one: the busy worker is terminated and the old promise cancelled", async () => {
    const client = new LayoutClient(factory);
    const first = client.layout(input(10, "a"));
    FakeWorker.created[0]!.ready(); // "a" is sent: the worker is computing it
    const second = client.layout(input(10, "b"));
    await expect(first).rejects.toBeInstanceOf(LayoutCancelled);
    const [w1, w2] = FakeWorker.created;
    expect(w1!.terminated).toBe(true);
    w1!.onmessage?.({ data: { type: "result", id: w1!.requests[0]!.id, positions: new Float64Array(20) } } as MessageEvent<LayoutResponse>); // late reply is ignored
    w2!.ready();
    w2!.answer();
    expect(Array.from(await second)).toEqual(Array.from(computeCoseLayout(input(10, "b"))));
  });

  it("a request made while the worker loads is held, a newer one replaces it, and the loading worker is kept", async () => {
    const client = new LayoutClient(factory);
    const first = client.layout(input(6, "a"));
    const second = client.layout(input(6, "b"));
    await expect(first).rejects.toBeInstanceOf(LayoutCancelled);
    const [worker] = FakeWorker.created;
    expect(FakeWorker.created).toHaveLength(1);
    expect(worker!.terminated).toBe(false); // never killed mid-load
    worker!.ready();
    expect(worker!.requests.map((r) => r.input.nodes[0]!.id)).toEqual(["b0"]); // only the latest is computed
    worker!.answer();
    expect(Array.from(await second)).toEqual(Array.from(computeCoseLayout(input(6, "b"))));
  });

  it("dispose() while the worker loads terminates it as soon as it is ready, without sending work", async () => {
    const client = new LayoutClient(factory);
    const job = client.layout(input(5));
    client.dispose();
    await expect(job).rejects.toBeInstanceOf(LayoutCancelled);
    const [worker] = FakeWorker.created;
    expect(worker!.terminated).toBe(false);
    worker!.ready();
    expect(worker!.terminated).toBe(true);
    expect(worker!.requests).toHaveLength(0);
  });

  it("dispose() terminates a computing worker and rejects pending and later requests", async () => {
    const client = new LayoutClient(factory);
    const job = client.layout(input(8));
    FakeWorker.created[0]!.ready();
    client.dispose();
    await expect(job).rejects.toBeInstanceOf(LayoutCancelled);
    expect(FakeWorker.created[0]!.terminated).toBe(true);
    await expect(client.layout(input(8, "z"))).rejects.toBeInstanceOf(LayoutCancelled);
  });

  it("a crashed worker finishes the job on the main thread and is not used again", async () => {
    const client = new LayoutClient(factory);
    const job = client.layout(input(9));
    FakeWorker.created[0]!.crash();
    expect(Array.from(await job)).toEqual(Array.from(computeCoseLayout(input(9))));
    await client.layout(input(9, "q"));
    expect(FakeWorker.created).toHaveLength(1);
  });

  it("without Worker support the layout runs in place", async () => {
    const client = new LayoutClient(null);
    expect(Array.from(await client.layout(input(7)))).toEqual(Array.from(computeCoseLayout(input(7))));
  });

  it("the cache keeps the most recently used 24 layouts", async () => {
    const client = new LayoutClient(null);
    for (let i = 0; i < 25; i++) await client.layout(input(3, `n${i}-`));
    expect(cachedLayout(layoutKey(input(3, "n0-")))).toBeUndefined();
    expect(cachedLayout(layoutKey(input(3, "n24-")))).toBeDefined();
  });
});
