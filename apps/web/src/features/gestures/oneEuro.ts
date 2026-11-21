/**
 * One Euro filter (Casiez, Roussel & Vogel, CHI 2012): an adaptive low-pass filter that removes
 * jitter when the hand is still and follows quickly when it moves. Independent implementation of
 * the published algorithm.
 */
export class OneEuroFilter {
  private x: number | null = null;
  private dx = 0;
  private t: number | null = null;

  constructor(
    private readonly minCutoff = 1.2,
    private readonly beta = 0.012,
    private readonly dCutoff = 1.0,
  ) {}

  private static alpha(cutoff: number, dtSeconds: number): number {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dtSeconds);
  }

  reset(): void {
    this.x = null;
    this.dx = 0;
    this.t = null;
  }

  /** Filter a sample taken at `tMs`. Non-increasing timestamps return the last value unchanged. */
  filter(value: number, tMs: number): number {
    if (this.x === null || this.t === null) {
      this.x = value;
      this.t = tMs;
      return value;
    }
    if (tMs <= this.t) return this.x;
    const dt = (tMs - this.t) / 1000;
    this.t = tMs;
    const rawDx = (value - this.x) / dt;
    this.dx = this.dx + OneEuroFilter.alpha(this.dCutoff, dt) * (rawDx - this.dx);
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
    this.x = this.x + OneEuroFilter.alpha(cutoff, dt) * (value - this.x);
    return this.x;
  }
}

export class PointFilter {
  private readonly fx: OneEuroFilter;
  private readonly fy: OneEuroFilter;

  constructor(minCutoff?: number, beta?: number) {
    this.fx = new OneEuroFilter(minCutoff, beta);
    this.fy = new OneEuroFilter(minCutoff, beta);
  }

  reset(): void {
    this.fx.reset();
    this.fy.reset();
  }

  filter(p: { x: number; y: number }, tMs: number): { x: number; y: number } {
    return { x: this.fx.filter(p.x, tMs), y: this.fy.filter(p.y, tMs) };
  }
}
