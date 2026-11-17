import { Icon } from "../../components/ui";
import { formatBp } from "../../lib/format";
import { t, tDynamic } from "../../lib/i18n";
import type { HypothesisAssessment, HypothesisItem, HypothesisTestItem } from "../../lib/types";

const VERDICT_TONE: Record<HypothesisAssessment["verdict"], "supports" | "weakens" | "unknown"> = {
  suspicious_explanation_favoured: "supports",
  benign_explanation_favoured: "weakens",
  inconclusive: "unknown",
  insufficient_data: "unknown",
};

const RESULT_TONE: Record<HypothesisTestItem["result"], { tone: string; icon: "check" | "minus" | "info" }> = {
  consistent: { tone: "supports", icon: "check" },
  inconsistent: { tone: "weakens", icon: "minus" },
  unavailable: { tone: "unknown", icon: "info" },
};

/** What was observed, in words. Only the fields the engine records; anything else is omitted. */
function observed(test: HypothesisTestItem): string | null {
  const o = test.observation as Record<string, unknown>;
  if (typeof o.recurrence_bp === "number") return t("hyp.obs.recurrence", { share: formatBp(o.recurrence_bp) });
  if (typeof o.span_bp === "number") return t("hyp.obs.span", { share: formatBp(o.span_bp) });
  if (typeof o.largest_day_bp === "number") return t("hyp.obs.largestDay", { share: formatBp(o.largest_day_bp) });
  if (typeof o.two_way_count === "number") return t("hyp.obs.twoWay", { count: o.two_way_count });
  if (typeof o.temporal_status === "string") return tDynamic("ev.", o.temporal_status);
  if (typeof o.peer_status === "string") return tDynamic("peer.status.", o.peer_status);
  return null;
}

function TestRow({ test }: { test: HypothesisTestItem }) {
  const { tone, icon } = RESULT_TONE[test.result];
  const obs = observed(test);
  return (
    <li className={`reason reason--${tone}`}>
      <span className="reason__mark" aria-hidden="true">
        <Icon name={icon} size={14} />
      </span>
      <div className="reason__body">
        <span>{tDynamic("hyp.expect.", test.expected)}</span>
        <span className="cell-note">{[obs, tDynamic("hyp.result.", test.result), tDynamic("hyp.group.", test.group)].filter(Boolean).join(" · ")}</span>
      </div>
    </li>
  );
}

function HypothesisRow({ h }: { h: HypothesisItem }) {
  const needs = h.required_data.map((d) => tDynamic("hyp.data.", d)).join(", ");
  return (
    <li className={`hyp hyp--${h.status}`} data-testid={`hyp-${h.hypothesis_id}`}>
      <div className="hyp__head">
        <span className="hyp__name">{tDynamic("hyp.id.", h.hypothesis_id)}</span>
        <span className={`hyp__status hyp__status--${h.status}`}>{tDynamic("hyp.status.", h.status)}</span>
      </div>
      <span className="hyp__polarity">{tDynamic("hyp.polarity.", h.polarity)}</span>
      {h.tests.length > 0 ? (
        <details className="disclosure disclosure--flat">
          <summary>
            <Icon name="chevronRight" size={16} className="disclosure__chevron" />
            <span>{t("hyp.tests", { consistent: h.consistent_groups, inconsistent: h.inconsistent_groups })}</span>
          </summary>
          <ul className="reason-list reason-list--compact">
            {h.tests.map((test) => (
              <TestRow key={test.test_id} test={test} />
            ))}
          </ul>
        </details>
      ) : (
        needs && <p className="ctx__note">{t("hyp.needs", { list: needs })}</p>
      )}
    </li>
  );
}

/**
 * Competing explanations for the formation (hypotheses-v1): the suspicious hypothesis and the
 * legitimate alternatives with the same shape, each with its falsification tests. Observations,
 * never a conclusion about a crime.
 */
export function CompetingExplanations({ assessment }: { assessment: HypothesisAssessment }) {
  const tone = VERDICT_TONE[assessment.verdict];
  const ordered = [...assessment.hypotheses].sort((a, b) => Number(a.polarity !== "suspicious") - Number(b.polarity !== "suspicious"));
  const missing = assessment.unavailable_information.map((d) => tDynamic("hyp.data.", d));
  return (
    <section className="ctx__section" data-testid="hypotheses" aria-labelledby="hyp-title">
      <h3 id="hyp-title" className={`ctx__label ctx__label--${tone}`}>
        {t("hyp.title")}
      </h3>
      <p className="hyp-verdict" data-testid="hyp-verdict">
        {tDynamic("hyp.verdict.", assessment.verdict)}
      </p>
      <ul className="hyp-list">
        {ordered.map((h) => (
          <HypothesisRow key={h.hypothesis_id} h={h} />
        ))}
      </ul>
      <p className="ctx__note">{t("hyp.hint")} {t("hyp.groupsNote")}</p>
      {missing.length > 0 && (
        <p className="ctx__note" data-testid="hyp-next">
          {t("hyp.nextChecks")}: {missing.join(", ")}.
        </p>
      )}
    </section>
  );
}
