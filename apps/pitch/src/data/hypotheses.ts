/**
 * Deterministic hypothesis scoring that mirrors the rules documented in
 * docs/architecture/HYPOTHESIS_ENGINE.md (branch of PR #3): each independent observation GROUP votes
 * +1 (consistent), -1 (inconsistent) or 0 (does not discriminate). Status and verdict follow the documented rules.
 * The observations below are illustrative; the rules are not. No probabilities are produced anywhere.
 */
export type Vote = -1 | 0 | 1;
export type HypId = "suspicious" | "legit";
export type Status = "supported" | "refuted" | "weakened" | "not_established";
export type Verdict = "suspicious_explanation_favoured" | "benign_explanation_favoured" | "inconclusive";
export type DatasetId = "A" | "B";

export interface Observation {
  group: string; // engine group id
  title: string; // Russian label
  rule: string; // the a-priori rule from configs/detectors.yaml, in words
  seen: Record<DatasetId, string>;
  votes: Record<DatasetId, Record<HypId, Vote>>;
}

export const OBSERVATIONS: Observation[] = [
  {
    group: "flow_timing",
    title: "Хронология потока",
    rule: "Вывод средств идёт после поступлений",
    seen: { A: "Вывод следует за поступлениями", B: "Вывод следует за поступлениями" },
    votes: { A: { suspicious: 1, legit: 0 }, B: { suspicious: 1, legit: 0 } },
  },
  {
    group: "subject_activity",
    title: "Период активности счёта",
    rule: "Охват ≥ 0,8 окна — устоявшийся; ≤ 0,3 — короткий",
    seen: { A: "Короткая вспышка внутри окна", B: "Активность на всём окне" },
    votes: { A: { suspicious: 1, legit: -1 }, B: { suspicious: -1, legit: 1 } },
  },
  {
    group: "counterparty_relationship",
    title: "Повторяемость контрагентов",
    rule: "≥ 0,5 платят в ≥ 2 разных дня — похоже на бизнес",
    seen: { A: "Каждый платил один раз", B: "Контрагенты платят в разные дни" },
    votes: { A: { suspicious: 1, legit: -1 }, B: { suspicious: -1, legit: 1 } },
  },
  {
    group: "two_way",
    title: "Встречные переводы",
    rule: "Возврат ≥ 10 % — двусторонняя связь",
    seen: { A: "Встречных переводов нет", B: "Встречных переводов нет" },
    votes: { A: { suspicious: 0, legit: 0 }, B: { suspicious: 0, legit: 0 } },
  },
];

export function statusOf(votes: Vote[]): Status {
  const consistent = votes.filter((v) => v === 1).length;
  const inconsistent = votes.filter((v) => v === -1).length;
  if (consistent >= 2 && inconsistent === 0) return "supported";
  if (inconsistent - consistent >= 2) return "refuted";
  if (inconsistent > 0) return "weakened";
  return "not_established";
}

export const balance = (votes: Vote[]) => votes.reduce<number>((a, v) => a + v, 0);

export interface Evaluation {
  status: Record<HypId, Status>;
  balance: Record<HypId, number>;
  verdict: Verdict;
}

export function evaluate(ds: DatasetId): Evaluation {
  const votes = (h: HypId) => OBSERVATIONS.map((o) => o.votes[ds][h]);
  const status = { suspicious: statusOf(votes("suspicious")), legit: statusOf(votes("legit")) };
  const bal = { suspicious: balance(votes("suspicious")), legit: balance(votes("legit")) };
  let verdict: Verdict = "inconclusive";
  if (status.legit === "supported" && bal.suspicious < 0) verdict = "benign_explanation_favoured";
  else if (status.suspicious === "supported" && bal.legit < 0) verdict = "suspicious_explanation_favoured";
  return { status, balance: bal, verdict };
}

/** Partition one hypothesis's observations into supporting / contradicting / not discriminating. */
export function partition(ds: DatasetId, h: HypId) {
  const rows = OBSERVATIONS.map((o) => ({ o, v: o.votes[ds][h] }));
  return {
    supports: rows.filter((r) => r.v === 1).map((r) => r.o),
    contradicts: rows.filter((r) => r.v === -1).map((r) => r.o),
    neutral: rows.filter((r) => r.v === 0).map((r) => r.o),
  };
}
