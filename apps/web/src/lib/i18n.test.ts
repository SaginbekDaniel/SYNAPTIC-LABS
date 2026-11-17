import { describe, expect, it } from "vitest";
import { reasonText, t } from "./i18n";

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
});
