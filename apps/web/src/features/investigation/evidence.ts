import { reasonFamily, reasonPolarity } from "../../lib/i18n";
import type { AlertDetail, EvidenceItem, ReasonCode } from "../../lib/types";

/**
 * Evidence is paired with reasons by signal family (reason-code prefix), never by evidence
 * kind alone: both temporal and peer findings can be `counterevidence`.
 */
export function evidenceOfFamily(family: ReturnType<typeof reasonFamily>, evidence: EvidenceItem[]): EvidenceItem | undefined {
  if (family === "other") return undefined;
  return evidence.find((e) => e.kind !== "coverage_fact" && reasonFamily(e.reason_code) === family);
}

export function evidenceForReason(code: string, evidence: EvidenceItem[]): EvidenceItem | undefined {
  return evidenceOfFamily(reasonFamily(code), evidence);
}

export type Stance = "supports" | "weakens" | "unknown";

/**
 * Where a reason sits in the analyst's argument. A band cap is a weakening finding (the policy
 * lowered priority because evidence was not good enough), even though its polarity is "limit".
 */
export function stanceOf(code: string): Stance {
  if (code.startsWith("BAND_CAPPED")) return "weakens";
  const p = reasonPolarity(code);
  return p === "for" ? "supports" : p === "against" ? "weakens" : "unknown";
}

export function groupReasons(alert: AlertDetail): Record<Stance, ReasonCode[]> {
  const out: Record<Stance, ReasonCode[]> = { supports: [], weakens: [], unknown: [] };
  for (const rc of alert.risk.reason_codes) out[stanceOf(rc.code)].push(rc as ReasonCode);
  return out;
}

/** All limitations stated by coverage and by the temporal/peer evidence, de-duplicated. */
export function limitationsOf(alert: AlertDetail): string[] {
  const temporal = evidenceOfFamily("temporal", alert.evidence);
  const peer = evidenceOfFamily("peer", alert.evidence);
  return [...new Set([...alert.coverage.limitations, ...(temporal?.limitations ?? []), ...(peer?.limitations ?? [])])];
}
