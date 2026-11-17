"""Hypothesis registry and falsification engine ``hypotheses-v1``.

Detectors are candidate generators: a funnel or fan-out says *where to look*, not *what
happened*. For each hub-type formation this module states the suspicious hypothesis and
the legitimate alternatives that produce the same shape, derives what each would predict,
and tests those predictions against observations. It never decides guilt.

Scoring (exact, deterministic):

* every test reads one *observation group*; tests in the same group are not independent
  and collapse to one vote (all consistent -> +1, all inconsistent -> -1, mixed -> 0);
* a hypothesis is ``supported`` with >= 2 consistent groups and none inconsistent,
  ``refuted`` when inconsistent groups exceed consistent ones by >= 2, ``weakened`` when
  any group is inconsistent, ``not_established`` otherwise, and ``untestable`` when no
  test can be evaluated on transaction data (the alternative stays listed, with the data
  that would test it);
* the formation verdict is ``benign_explanation_favoured`` only when a legitimate
  hypothesis is supported *and* the suspicious one has a negative balance;
  ``suspicious_explanation_favoured`` only when the suspicious hypothesis is supported and
  every testable alternative has a negative balance; ``insufficient_data`` when fewer than
  two groups could be evaluated for the suspicious hypothesis; ``inconclusive`` otherwise.

"Favoured" is relative to the *testable* alternatives. Untestable alternatives (one-off
legitimate collections such as ticket sales, personal remittances) are always reported,
so a suspicious verdict never reads as proof.

Observation groups and why they are separate:

* ``flow_timing`` — the temporal flow engine (did received funds move on within the lag);
* ``subject_activity`` — the subject's peer-relative turnover concentration *and* its
  activity span in the snapshot. Both derive from the same activity dates, so they share
  one group;
* ``counterparty_relationship`` — whether counterparties on the defining side transact
  with the subject on several distinct days (recurring relationship) or once;
* ``payout_schedule`` — whether a distribution is one payment run on one day;
* ``two_way`` — counterparties that also transact in the opposite direction.

Thresholds are fixed round values chosen before evaluation (majority, 20 %, 30 %/80 % of
the window, 90 %); they are documented hypotheses, not fitted parameters.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any

from nexora.analytics.graph_builder import CurrencyGraph
from nexora.domain.analysis import (
    Evidence,
    HypothesisAssessment,
    HypothesisEvaluation,
    HypothesisStatus,
    HypothesisTest,
    Polarity,
    TestResult,
    Verdict,
)
from nexora.domain.ids import canonical_json, sha256_hex, stable_uuid
from nexora.domain.transfers import ObservedTransfer

REGISTRY_VERSION = "hypotheses-v1"
HUB_KINDS = ("funnel", "fan_out")


@dataclass(frozen=True)
class HypothesisSpec:
    hypothesis_id: str
    version: str
    polarity: Polarity
    kinds: tuple[str, ...]
    description: str
    required_data: tuple[str, ...]
    testable: bool = True


#: Typed, versioned registry. Ids are stable API vocabulary (localised in the UI).
REGISTRY: tuple[HypothesisSpec, ...] = (
    HypothesisSpec(
        "collection_through_intermediary",
        "1",
        "suspicious",
        ("funnel",),
        "Funds from several unrelated senders are consolidated and moved on.",
        ("account_ownership_kyc", "counterparty_relationships"),
    ),
    HypothesisSpec(
        "coordinated_distribution",
        "1",
        "suspicious",
        ("fan_out",),
        "Received funds are split quickly across many recipients.",
        ("account_ownership_kyc", "recipient_onward_history"),
    ),
    HypothesisSpec(
        "recurring_business_activity",
        "1",
        "legitimate",
        ("funnel", "fan_out"),
        "A business with recurring customers or payees (settlement, supplier, rent, treasury).",
        ("merchant_category", "business_registration"),
    ),
    HypothesisSpec(
        "scheduled_payout",
        "1",
        "legitimate",
        ("fan_out",),
        "A payroll or supplier run paid from an existing balance on a schedule.",
        ("employer_or_payer_registration",),
    ),
    HypothesisSpec(
        "loan_disbursement_and_repayment",
        "1",
        "legitimate",
        ("funnel", "fan_out"),
        "Two-way lending relationships: disbursements and instalments.",
        ("loan_agreements",),
    ),
    HypothesisSpec(
        "one_off_legitimate_collection",
        "1",
        "legitimate",
        ("funnel",),
        "Ticket sales, fundraising or group purchases: one-off payers and a prompt payout.",
        ("merchant_category", "payment_purpose_references"),
        testable=False,
    ),
    HypothesisSpec(
        "personal_remittance",
        "1",
        "legitimate",
        ("fan_out",),
        "A person sending parts of an income to relatives.",
        ("kyc_relationship_data", "income_source"),
        testable=False,
    ),
)


@dataclass(frozen=True)
class HubContext:
    """Inputs the engine needs about one hub formation; everything comes from the snapshot."""

    formation_id: str
    kind: str
    subject: str
    counterparties: tuple[str, ...]  # feeders (funnel) or recipients (fan-out)
    two_way_counterparties: tuple[str, ...]
    temporal_status: str
    temporal_evidence_id: str
    peer_status: str | None
    peer_evidence_id: str | None
    window: tuple[date, date]  # snapshot window


def _bp(num: int, den: int) -> int:
    return 0 if den <= 0 else num * 10_000 // den


class HypothesisEngine:
    def __init__(self, cfg: dict[str, Any], transfers: dict[str, ObservedTransfer]):
        self.cfg = cfg
        self.transfers = transfers
        self.recurring_min_days = int(cfg["recurring_min_days"])
        self.recurrence_high = Fraction(str(cfg["recurrence_high"]))
        self.recurrence_low = Fraction(str(cfg["recurrence_low"]))
        self.span_established = Fraction(str(cfg["span_established"]))
        self.span_short = Fraction(str(cfg["span_short"]))
        self.single_run = Fraction(str(cfg["single_run_share"]))
        self.config_sha256 = sha256_hex(canonical_json(cfg))

    # -- observations (each becomes validated, recomputable evidence) -----------------------
    def _counterparty_evidence(self, cg: CurrencyGraph, ctx: HubContext) -> Evidence:
        incoming = ctx.kind == "funnel"
        rows: list[dict[str, Any]] = []
        tx_ids: list[str] = []
        for acc in sorted(ctx.counterparties):
            edge = cg.edges[(acc, ctx.subject)] if incoming else cg.edges[(ctx.subject, acc)]
            days = {self.transfers[t].observed_date for t in edge.transaction_ids}
            rows.append({"account_id": acc, "transfer_count": len(edge.transaction_ids), "distinct_days": len(days)})
            tx_ids.extend(edge.transaction_ids)
        recurring = sum(1 for r in rows if int(r["distinct_days"]) >= self.recurring_min_days)
        return Evidence(
            id=stable_uuid("evidence", ctx.formation_id, "hyp_counterparties"),
            kind="aggregate_fact",
            reason_code="HYP_COUNTERPARTY_RECURRENCE",
            subject_id=ctx.formation_id,
            transaction_ids=tuple(sorted(tx_ids)),
            account_ids=(ctx.subject, *sorted(ctx.counterparties)),
            observations={
                "account_id": ctx.subject,
                "side": "incoming" if incoming else "outgoing",
                "counterparty_count": len(rows),
                "recurring_count": recurring,
                "recurrence_bp": _bp(recurring, len(rows)),
                "counterparties": rows,
                "total_minor": str(sum(self.transfers[t].amount_minor for t in tx_ids)),
            },
            thresholds={
                "recurring_min_days": self.recurring_min_days,
                "recurrence_high": str(self.recurrence_high),
                "recurrence_low": str(self.recurrence_low),
            },
            limitations=("relationship_purpose_unknown",),
            detector_version=REGISTRY_VERSION,
        )

    def _activity_evidence(self, cg: CurrencyGraph, ctx: HubContext) -> Evidence:
        mine = sorted(
            (
                self.transfers[t]
                for (snd, rcv), e in cg.edges.items()
                if ctx.subject in (snd, rcv)
                for t in e.transaction_ids
            ),
            key=lambda t: (t.observed_date, t.transaction_id),
        )
        first, last = mine[0], mine[-1]
        window_days = (ctx.window[1] - ctx.window[0]).days + 1
        span_days = (last.observed_date - first.observed_date).days + 1
        return Evidence(
            id=stable_uuid("evidence", ctx.formation_id, "hyp_activity"),
            kind="aggregate_fact",
            reason_code="HYP_ACTIVITY_SPAN",
            subject_id=ctx.formation_id,
            transaction_ids=tuple(dict.fromkeys((first.transaction_id, last.transaction_id))),
            account_ids=(ctx.subject,),
            observations={
                "account_id": ctx.subject,
                "first_seen": first.observed_date.isoformat(),
                "last_seen": last.observed_date.isoformat(),
                "active_days": len({t.observed_date for t in mine}),
                "span_days": span_days,
                "window_start": ctx.window[0].isoformat(),
                "window_end": ctx.window[1].isoformat(),
                "window_days": window_days,
                "span_bp": _bp(span_days, window_days),
            },
            thresholds={"span_short": str(self.span_short), "span_established": str(self.span_established)},
            limitations=("history_before_window_unobserved",),
            detector_version=REGISTRY_VERSION,
        )

    def _schedule_evidence(self, cg: CurrencyGraph, ctx: HubContext) -> Evidence:
        by_day: dict[date, int] = defaultdict(int)
        tx_ids: list[str] = []
        for acc in sorted(ctx.counterparties):
            for t in cg.edges[(ctx.subject, acc)].transaction_ids:
                by_day[self.transfers[t].observed_date] += self.transfers[t].amount_minor
                tx_ids.append(t)
        total = sum(by_day.values())
        top_day, top = max(sorted(by_day.items()), key=lambda kv: kv[1])
        return Evidence(
            id=stable_uuid("evidence", ctx.formation_id, "hyp_schedule"),
            kind="aggregate_fact",
            reason_code="HYP_PAYOUT_SCHEDULE",
            subject_id=ctx.formation_id,
            transaction_ids=tuple(sorted(tx_ids)),
            account_ids=(ctx.subject, *sorted(ctx.counterparties)),
            observations={
                "account_id": ctx.subject,
                "distinct_days": len(by_day),
                "largest_day": top_day.isoformat(),
                "largest_day_minor": str(top),
                "largest_day_bp": _bp(top, total),
                "total_minor": str(total),
            },
            thresholds={"single_run_share": str(self.single_run)},
            limitations=("payment_purpose_unknown",),
            detector_version=REGISTRY_VERSION,
        )

    # -- tests --------------------------------------------------------------------------------
    @staticmethod
    def _test(
        test_id: str, group: str, expected: str, result: TestResult, observation: dict[str, Any], *ev: str | None
    ) -> HypothesisTest:
        return HypothesisTest(test_id, group, observation, expected, result, tuple(e for e in ev if e))

    def _three_way(self, value: Fraction, low: Fraction, high: Fraction, *, high_is: TestResult) -> TestResult:
        low_is: TestResult = "inconsistent" if high_is == "consistent" else "consistent"
        if value >= high:
            return high_is
        if value <= low:
            return low_is
        return "unavailable"

    def evaluate(self, cg: CurrencyGraph, ctx: HubContext) -> tuple[HypothesisAssessment, list[Evidence]]:
        cp_ev = self._counterparty_evidence(cg, ctx)
        act_ev = self._activity_evidence(cg, ctx)
        evidence = [cp_ev, act_ev]
        recurrence = Fraction(cp_ev.observations["recurrence_bp"], 10_000)
        span = Fraction(act_ev.observations["span_bp"], 10_000)
        outcome: dict[str, TestResult] = {"supported": "consistent", "contradicted": "inconsistent"}
        timing: TestResult = outcome.get(ctx.temporal_status, "unavailable")
        conc: TestResult = outcome.get(ctx.peer_status or "", "unavailable")
        flip: dict[TestResult, TestResult] = {
            "consistent": "inconsistent",
            "inconsistent": "consistent",
            "unavailable": "unavailable",
        }

        rec_obs = {"recurrence_bp": cp_ev.observations["recurrence_bp"]}
        span_obs = {"span_bp": act_ev.observations["span_bp"]}
        one_off = self._three_way(recurrence, self.recurrence_low, self.recurrence_high, high_is="inconsistent")
        short = self._three_way(span, self.span_short, self.span_established, high_is="inconsistent")

        suspicious_tests = (
            self._test("onward_within_lag", "flow_timing", "funds_move_on_promptly", timing,
                       {"temporal_status": ctx.temporal_status}, ctx.temporal_evidence_id),
            self._test("turnover_concentrated", "subject_activity", "turnover_concentrated_in_time",
                       conc, {"peer_status": ctx.peer_status}, ctx.peer_evidence_id),
            self._test("short_lived_activity", "subject_activity", "short_lived_activity", short, span_obs, act_ev.id),
            self._test("one_off_counterparties", "counterparty_relationship", "one_off_counterparties", one_off,
                       rec_obs, cp_ev.id),
        )  # fmt: skip
        business_tests = (
            self._test("steady_turnover", "subject_activity", "turnover_steady_over_time",
                       flip[conc], {"peer_status": ctx.peer_status}, ctx.peer_evidence_id),
            self._test("established_activity", "subject_activity", "established_activity", flip[short], span_obs,
                       act_ev.id),
            self._test("recurring_counterparties", "counterparty_relationship", "recurring_counterparties",
                       flip[one_off], rec_obs, cp_ev.id),
        )  # fmt: skip
        two_way_result: TestResult = "consistent" if ctx.two_way_counterparties else "inconsistent"
        loan_tests = (
            self._test("two_way_relationships", "two_way", "counterparties_also_pay_back", two_way_result,
                       {"two_way_count": len(ctx.two_way_counterparties)}),
        )  # fmt: skip

        tests_by_id: dict[str, tuple[HypothesisTest, ...]] = {
            "collection_through_intermediary": suspicious_tests,
            "coordinated_distribution": suspicious_tests,
            "recurring_business_activity": business_tests,
            "loan_disbursement_and_repayment": loan_tests,
        }
        if ctx.kind == "fan_out":
            sched_ev = self._schedule_evidence(cg, ctx)
            evidence.append(sched_ev)
            share = Fraction(sched_ev.observations["largest_day_bp"], 10_000)
            run: TestResult = "consistent" if share >= self.single_run else "unavailable"
            if share < Fraction(1, 2) and sched_ev.observations["distinct_days"] >= 3:
                run = "inconsistent"
            tests_by_id["scheduled_payout"] = (
                self._test("single_payment_run", "payout_schedule", "paid_as_one_run", run,
                           {"largest_day_bp": sched_ev.observations["largest_day_bp"]}, sched_ev.id),
                self._test("funded_in_advance", "flow_timing", "funded_from_existing_balance", flip[timing],
                           {"temporal_status": ctx.temporal_status}, ctx.temporal_evidence_id),
            )  # fmt: skip

        evaluations = tuple(
            _score(spec, tests_by_id.get(spec.hypothesis_id, ())) for spec in REGISTRY if ctx.kind in spec.kinds
        )
        verdict = _verdict(evaluations)
        cited = {ctx.temporal_evidence_id} | ({ctx.peer_evidence_id} if ctx.peer_evidence_id else set())
        unavailable = sorted(
            {d for h in evaluations if h.status in ("untestable", "not_established") for d in h.required_data}
        )
        assessment = HypothesisAssessment(
            id=stable_uuid("hypotheses", ctx.formation_id, REGISTRY_VERSION, self.config_sha256),
            formation_id=ctx.formation_id,
            registry_version=REGISTRY_VERSION,
            config_sha256=self.config_sha256,
            verdict=verdict,
            hypotheses=evaluations,
            subject_ids=(ctx.subject, *sorted(ctx.counterparties)),
            transaction_ids=tuple(sorted({t for e in evidence for t in e.transaction_ids})),
            evidence_ids=tuple(sorted({e.id for e in evidence} | cited)),
            unavailable_information=tuple(unavailable),
        )
        return assessment, evidence


def _score(spec: HypothesisSpec, tests: tuple[HypothesisTest, ...]) -> HypothesisEvaluation:
    if not spec.testable:
        return HypothesisEvaluation(
            spec.hypothesis_id, spec.version, spec.polarity, "untestable", 0, 0, (), spec.required_data
        )
    groups: dict[str, set[str]] = defaultdict(set)
    for t in tests:
        if t.result != "unavailable":
            groups[t.group].add(t.result)
    consistent = sum(1 for r in groups.values() if r == {"consistent"})
    inconsistent = sum(1 for r in groups.values() if r == {"inconsistent"})
    status: HypothesisStatus
    if not groups:
        status = "untestable"
    elif consistent >= 2 and inconsistent == 0:
        status = "supported"
    elif inconsistent - consistent >= 2:
        status = "refuted"
    elif inconsistent:
        status = "weakened"
    else:
        status = "not_established"
    return HypothesisEvaluation(
        spec.hypothesis_id, spec.version, spec.polarity, status, consistent, inconsistent, tests, spec.required_data
    )


def _verdict(evaluations: tuple[HypothesisEvaluation, ...]) -> Verdict:
    suspicious = next(h for h in evaluations if h.polarity == "suspicious")
    benign = [h for h in evaluations if h.polarity == "legitimate" and h.status != "untestable"]
    balance = suspicious.consistent_groups - suspicious.inconsistent_groups
    if suspicious.consistent_groups + suspicious.inconsistent_groups < 2:
        return "insufficient_data"
    if any(h.status == "supported" for h in benign) and balance < 0:
        return "benign_explanation_favoured"
    if suspicious.status == "supported" and all(h.consistent_groups - h.inconsistent_groups < 0 for h in benign):
        return "suspicious_explanation_favoured"
    return "inconclusive"
