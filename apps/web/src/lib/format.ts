/**
 * Exact money formatting. Amounts arrive as decimal strings of integer minor units and
 * are handled with BigInt only — never parseFloat/Number (ADR-003).
 */

const CURRENCY_SYMBOL: Record<string, string> = { KZT: "₸", USD: "$", EUR: "€", RUB: "₽" };
const intFmt = new Intl.NumberFormat("ru-RU");

export function parseMinor(value: string): bigint {
  if (!/^-?\d+$/.test(value)) throw new Error(`invalid minor-unit amount: ${value}`);
  return BigInt(value);
}

export function formatMoney(minor: string | bigint, currency = "KZT", opts: { fraction?: boolean } = {}): string {
  const v = typeof minor === "bigint" ? minor : parseMinor(minor);
  const neg = v < 0n;
  const abs = neg ? -v : v;
  const whole = abs / 100n;
  const frac = (abs % 100n).toString().padStart(2, "0");
  const showFrac = opts.fraction ?? frac !== "00";
  const body = intFmt.format(whole) + (showFrac ? `,${frac}` : "");
  const sym = CURRENCY_SYMBOL[currency] ?? currency;
  return `${neg ? "−" : ""}${body} ${sym}`;
}

export function sumMinor(values: readonly string[]): bigint {
  return values.reduce((acc, v) => acc + parseMinor(v), 0n);
}

/** Basis points (integer) → percent string, e.g. 9350 → "93,5 %". */
export function formatBp(bp: number): string {
  const pct = Math.floor(bp / 10) / 10;
  return `${pct.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} %`;
}

const dateFmt = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
const dateTimeFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

/** A calendar date from the source ("YYYY-MM-DD"); formatted in UTC so it never shifts a day. */
export function formatDate(isoDate: string): string {
  return dateFmt.format(new Date(`${isoDate}T00:00:00Z`));
}

export function formatDateTime(iso: string): string {
  return `${dateTimeFmt.format(new Date(iso))} UTC`;
}

/** Event time honouring source precision: day-only records never show a clock time. */
export function formatEventTime(observedDate: string, occurredAt: string | null | undefined): string {
  return occurredAt ? formatDateTime(occurredAt) : formatDate(observedDate);
}

export function shortId(id: string, keep = 8): string {
  return id.length <= keep * 2 + 1 ? id : `${id.slice(0, keep)}…${id.slice(-4)}`;
}

/** Ratio in [0, 1] as a percentage; `null` (undefined metric, zero denominator) stays visible. */
export function formatRatio(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "н/д";
  return `${(value * 100).toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
}
