import type { components } from "../../lib/api-types";

export const TRANSFER_API = "/api/v1/demo/transfer-checks";
export const TRANSFER_ROUTE = "/lab/transfer-protection";

export type ScenarioOption = components["schemas"]["ScenarioOption"];
export type CheckRequest = components["schemas"]["TransferCheckRequest"];
export type CheckResult = components["schemas"]["TransferCheckResponse"];
export type AssessmentLink = components["schemas"]["TransferEvidenceRequest"];
export type AssessmentEvidence = components["schemas"]["TransferEvidenceResponse"];

export function toTenge(minor: string): string {
  const padded = minor.padStart(3, "0");
  return `${padded.slice(0, -2)},${padded.slice(-2)}`;
}

export function toMinorUnits(tenge: string): string | null {
  const match = /^([0-9]{1,36})(?:[.,]([0-9]{1,2}))?$/.exec(tenge.trim());
  if (!match) return null;
  const minor = BigInt(`${match[1]}${(match[2] ?? "").padEnd(2, "0")}`);
  return minor > 0n ? minor.toString() : null;
}
