"""Coverage assessment, abstention inputs and next-best-data requests (spec §12).

Coverage states may co-occur, so they are a list, not an enum. Unknown observation is
never treated as zero: an account at a declared collection boundary is not a proven
terminal, and a centre without observed outflow is not proven to retain funds.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nexora.analytics.temporal.flow import FlowResult
from nexora.domain.analysis import CoverageAssessment, DataRequest
from nexora.domain.transfers import ObservedTransfer


def assess_coverage(
    *,
    kind: str,
    subject_account_id: str,
    member_ids: tuple[str, ...],
    entry_ids: tuple[str, ...],
    has_downstream: bool,
    transfers: list[ObservedTransfer],
    flow: FlowResult | None,
    contract: dict[str, Any],
    window: tuple[date, date],
) -> CoverageAssessment:
    boundary = set(contract.get("boundary_account_ids") or [])
    limitations: list[str] = ["missing_context"]  # no ownership / purpose / business category data
    subject_limitations: list[str] = []
    requests: list[DataRequest] = []
    start, end = window
    follow_window = (start.isoformat(), (end + timedelta(days=30)).isoformat())

    if any(t.precision == "day" for t in transfers):
        limitations.append("timestamp_precision_limited")
    boundary_members = tuple(sorted(m for m in member_ids if m in boundary))
    if boundary_members:
        limitations.append("boundary_limited")
        if subject_account_id in boundary:
            subject_limitations.append("boundary_limited")
            requests.append(
                DataRequest(
                    type="outgoing_history_beyond_boundary",
                    subject_ids=(subject_account_id,),
                    proposed_window=follow_window,
                    missing_dependency="boundary_limited",
                    expected_resolution="determine_onward_movement",
                    priority_heuristic=1,
                )
            )
    if contract.get("upstream_observed") is False:
        limitations.append("upstream_unknown")
        requests.append(
            DataRequest(
                type="incoming_history_for_entry_accounts",
                subject_ids=tuple(sorted(entry_ids)),
                proposed_window=((start - timedelta(days=30)).isoformat(), end.isoformat()),
                missing_dependency="upstream_unknown",
                expected_resolution="identify_funding_sources",
                priority_heuristic=3,
            )
        )
    if kind == "funnel" and not has_downstream:
        limitations.append("downstream_unobserved")
        if subject_account_id not in boundary:
            requests.append(
                DataRequest(
                    type="outgoing_history_for_center",
                    subject_ids=(subject_account_id,),
                    proposed_window=follow_window,
                    missing_dependency="downstream_unobserved",
                    expected_resolution="determine_onward_movement",
                    priority_heuristic=2,
                )
            )
    if flow is not None and flow.status == "possible_ambiguous" and flow.precision != "timestamp":
        requests.append(
            DataRequest(
                type="exact_timestamps",
                subject_ids=flow.supporting_transaction_ids,
                proposed_window=None,
                missing_dependency="timestamp_precision_limited",
                expected_resolution="order_same_day_transfers",
                priority_heuristic=1,
            )
        )
    requests.sort(key=lambda r: (r.priority_heuristic, r.type))
    return CoverageAssessment(
        limitations=tuple(dict.fromkeys(limitations)),
        subject_limitations=tuple(subject_limitations),
        boundary_accounts=boundary_members,
        data_requests=tuple(requests),
    )
