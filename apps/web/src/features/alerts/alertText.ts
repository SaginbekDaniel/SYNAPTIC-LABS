import { shortId } from "../../lib/format";
import { reasonText, t, tDynamic } from "../../lib/i18n";
import type { AlertSummary, Band, ReasonCode } from "../../lib/types";

export const BAND_ORDER: Band[] = ["critical", "high", "medium", "insufficient_evidence"];

/** Colour token per band, shared by charts and badges. */
export const BAND_COLOR: Record<Band, string> = {
  critical: "var(--band-critical)",
  high: "var(--band-high)",
  medium: "var(--band-medium)",
  low: "var(--band-low)",
  insufficient_evidence: "var(--band-unresolved)",
};

/**
 * Human-readable title: what the network does, plus a short handle for the centre account.
 * The exact account id is always shown next to it (never replaced).
 */
export function alertTitle(a: Pick<AlertSummary, "formation">): string {
  return t("alert.title", { kind: tDynamic("kind.", a.formation.kind), handle: accountHandle(a.formation.subject_account_id) });
}

/** "··7530": a short spoken handle for an opaque id; the full id stays visible elsewhere. */
export function accountHandle(id: string): string {
  return id.length > 6 ? `··${id.slice(-4)}` : id;
}

/** The one-line "why": the structural observation in plain language. */
export function alertWhy(a: Pick<AlertSummary, "risk" | "formation">): string | null {
  const rc = a.risk.reason_codes.find((r) => r.code.startsWith("STRUCT_"));
  return rc ? reasonText(rc as ReasonCode, a.formation.currency) : null;
}

/** Case titles are stored as "kind:account"; render them like alert titles. */
export function caseTitle(raw: string): { title: string; account: string | null } {
  const i = raw.indexOf(":");
  if (i <= 0) return { title: raw, account: null };
  const kind = raw.slice(0, i);
  const account = raw.slice(i + 1);
  return { title: t("alert.title", { kind: tDynamic("kind.", kind, kind), handle: accountHandle(account) }), account };
}

export function compactId(id: string): string {
  return shortId(id, 6);
}
