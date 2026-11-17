import { describe, expect, it } from "vitest";
import { reasonFamily, reasonPolarity, reasonText, t } from "./i18n";

describe("i18n plurals", () => {
  it("agrees Russian plural forms", () => {
    expect(t("alerts.accounts", { count: 1 })).toBe("1 счёт");
    expect(t("alerts.accounts", { count: 2 })).toBe("2 счёта");
    expect(t("alerts.accounts", { count: 5 })).toBe("5 счетов");
    expect(t("alerts.accounts", { count: 21 })).toBe("21 счёт");
    expect(t("alerts.accounts", { count: 12 })).toBe("12 счетов");
  });
  it("renders reasons from numeric params without double punctuation", () => {
    const text = reasonText({
      code: "TEMPORAL_PASS_THROUGH_SUPPORTED",
      params: { compatible_minor: "247733194", entry_minor: "302113614", fraction_bp: 8190, lag_days_min: 3, lag_days_max: 5, precision: "day" },
    });
    expect(text).toContain("2 477 331,94 ₸");
    expect(text.endsWith("3–5 дн.")).toBe(true);
  });
  it("falls back for unknown reason codes instead of crashing", () => {
    expect(reasonText({ code: "FUTURE_CODE", params: {} })).toContain("FUTURE_CODE");
  });
  it("renders peer-statistics reasons and classifies their direction", () => {
    const outlier = { code: "PEER_CONCENTRATION_OUTLIER", params: { burst_bp: 10000, window_days: 3, cohort_size: 41, fence_bp: 8125 } };
    expect(reasonText(outlier).replace(/\s/g, " ")).toBe("100 % оборота счёта пришлось на 3 дня — выше порога группы сравнения (81,2 %, 41 счёт).");
    expect(reasonPolarity("PEER_CONCENTRATION_OUTLIER")).toBe("for");
    expect(reasonPolarity("PEER_TYPICAL_TURNOVER")).toBe("against");
    expect(reasonFamily("PEER_TYPICAL_TURNOVER")).toBe("peer");
    expect(reasonFamily("TEMPORAL_CONTRADICTED")).toBe("temporal");
  });
  it("renders v2 structural reasons with exact money", () => {
    expect(reasonText({ code: "STRUCT_CYCLE_LOOP", params: { length: 4, currency: "KZT" } })).toContain("4 транзитных счетов");
    const fan = reasonText({ code: "STRUCT_FAN_OUT_RECIPIENTS", params: { count: 6, total_minor: "900719925474099301", currency: "KZT" } });
    expect(fan.replace(/\s/g, " ")).toContain("9 007 199 254 740 993,01 ₸"); // beyond 2^53, no float rounding
  });
  it("explains which evidence gate capped the band", () => {
    const v2 = reasonText({ code: "BAND_CAPPED_BY_EVIDENCE", params: { from: "high", to: "medium", gates: ["peer_contradicted"] } });
    expect(v2).toBe("Приоритет ограничен: «Высокий» → «Средний», потому что оборот счёта типичен для группы сравнения.");
    expect(reasonText({ code: "BAND_CAPPED_BY_EVIDENCE", params: { from: "high", to: "medium" } })).toContain("качества доказательств");
  });
});

describe("competing explanations (hypotheses-v1)", () => {
  const ids = [
    "collection_through_intermediary",
    "coordinated_distribution",
    "recurring_business_activity",
    "scheduled_payout",
    "loan_disbursement_and_repayment",
    "one_off_legitimate_collection",
    "personal_remittance",
  ];
  it("localises every registry hypothesis, verdict and gate", () => {
    for (const id of ids) expect(t(`hyp.id.${id}` as Parameters<typeof t>[0])).not.toContain("hyp.");
    for (const v of ["suspicious_explanation_favoured", "benign_explanation_favoured", "inconclusive", "insufficient_data"]) {
      expect(reasonText({ code: "HYPOTHESIS_VERDICT", params: { verdict: v } })).not.toContain("hyp.");
    }
    const capped = reasonText({ code: "BAND_CAPPED_BY_EVIDENCE", params: { from: "medium", to: "low", gates: ["hypothesis_benign_explanation_favoured"] } });
    expect(capped).toContain("законное объяснение");
  });
  it("never claims a crime was committed or proven", () => {
    const copy = ["hyp.title", "hyp.hint", "hyp.verdict.suspicious_explanation_favoured", "hyp.verdict.benign_explanation_favoured"].map((k) =>
      t(k as Parameters<typeof t>[0]).toLowerCase(),
    );
    for (const text of copy) expect(text).not.toMatch(/отмыв|мошенни|доказан|преступ/);
    expect(t("hyp.verdict.suspicious_explanation_favoured")).toContain("не исключены");
  });
});
