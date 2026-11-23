/**
 * Main-thread side of the layout worker.
 *
 * One client per graph canvas: it owns at most one worker and one job. A new request supersedes the
 * previous one; if the superseded job is already computing, the worker is terminated (a 300-node cose run
 * takes seconds and its result would be thrown away) and a fresh one is started on demand. Work is sent
 * only after the worker reports "ready" (module loaded); a job that has not been sent yet is simply
 * replaced, and a still-loading worker is never killed mid-load (it would leave its module requests
 * dangling). dispose() terminates the worker — a loading one as soon as it is ready — so nothing keeps
 * computing after the canvas is gone.
 *
 * Results are cached by layoutKey (everything that determines them), so returning to a view, toggling a
 * filter back or remounting the canvas shows the stored picture at once. If workers are unavailable or
 * the worker fails, the layout runs on the main thread instead (correct, just not off-thread).
 */
import { computeCoseLayout, layoutKey, type LayoutInput, type LayoutPositions } from "./coseLayout";
import type { LayoutRequest, LayoutResponse } from "./layoutWorker";

const CACHE_LIMIT = 24;
const cache = new Map<string, LayoutPositions>();

export function cachedLayout(key: string): LayoutPositions | undefined {
  const hit = cache.get(key);
  if (hit) {
    cache.delete(key); // most recently used goes last
    cache.set(key, hit);
  }
  return hit;
}

function remember(key: string, positions: LayoutPositions): void {
  cache.set(key, positions);
  while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
}

/** Tests only. */
export function clearLayoutCache(): void {
  cache.clear();
}

export class LayoutCancelled extends Error {
  constructor() {
    super("layout cancelled");
  }
}

type WorkerFactory = () => Worker;
const defaultFactory: WorkerFactory = () =>
  new Worker(new URL("./layoutWorker.ts", import.meta.url), { type: "module", name: "nexora-graph-layout" });

interface Job {
  id: number;
  key: string;
  input: LayoutInput;
  /** Posted to the worker (so the worker may be computing it). */
  sent: boolean;
  resolve: (p: LayoutPositions) => void;
  reject: (e: Error) => void;
}

export class LayoutClient {
  private worker: Worker | null = null;
  private workerReady = false;
  private job: Job | null = null;
  private nextId = 1;
  private disposed = false;
  /** Set when a worker failed to load or crashed: later layouts run in place. */
  private workerFailed = false;

  constructor(private readonly createWorker: WorkerFactory | null = typeof Worker === "undefined" ? null : defaultFactory) {}

  /** Positions for `input` (cached, from the worker, or computed in place as a fallback). */
  layout(input: LayoutInput): Promise<LayoutPositions> {
    if (this.disposed) return Promise.reject(new LayoutCancelled());
    this.cancel();
    const key = layoutKey(input);
    const hit = cachedLayout(key);
    if (hit) return Promise.resolve(hit);
    return new Promise<LayoutPositions>((resolve, reject) => {
      const job: Job = { id: this.nextId++, key, input, sent: false, resolve, reject };
      this.job = job;
      const worker = this.ensureWorker();
      if (!worker) this.runInPlace(job);
      else this.send();
    });
  }

  /** Abandon the current job, if any. A worker that may be computing it is terminated; a loading one is kept. */
  cancel(): void {
    const job = this.job;
    if (!job) return;
    this.job = null;
    if (job.sent) this.terminate();
    job.reject(new LayoutCancelled());
  }

  dispose(): void {
    this.disposed = true;
    this.cancel();
    if (this.workerReady) this.terminate(); // otherwise on "ready" (see receive)
  }

  private send(): void {
    const job = this.job;
    if (!job || job.sent || !this.worker || !this.workerReady) return;
    job.sent = true;
    const msg: LayoutRequest = { id: job.id, input: job.input };
    this.worker.postMessage(msg);
  }

  private ensureWorker(): Worker | null {
    if (this.worker || !this.createWorker || this.workerFailed) return this.worker;
    try {
      const worker = this.createWorker();
      worker.onmessage = (e: MessageEvent<LayoutResponse>) => this.receive(e.data);
      // A worker that cannot load or crashes: finish the current job on the main thread, use no worker after.
      worker.onerror = (e) => {
        e.preventDefault?.();
        this.workerFailed = true;
        this.terminate();
        const job = this.job;
        if (job) this.runInPlace(job);
      };
      this.worker = worker;
    } catch {
      return null;
    }
    return this.worker;
  }

  private terminate(): void {
    this.worker?.terminate();
    this.worker = null;
    this.workerReady = false;
  }

  private receive(m: LayoutResponse): void {
    if (m.type === "ready") {
      this.workerReady = true;
      if (this.disposed) this.terminate();
      else this.send();
      return;
    }
    const job = this.job;
    if (!job || m.id !== job.id) return; // a reply to a superseded job
    if (m.type === "error") {
      this.runInPlace(job);
      return;
    }
    this.job = null;
    remember(job.key, m.positions);
    job.resolve(m.positions);
  }

  private runInPlace(job: Job): void {
    if (this.job !== job) return;
    this.job = null;
    try {
      const positions = computeCoseLayout(job.input);
      remember(job.key, positions);
      job.resolve(positions);
    } catch (err) {
      job.reject(err instanceof Error ? err : new Error(String(err)));
    }
  }
}
