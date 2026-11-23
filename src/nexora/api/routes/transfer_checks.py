"""Customer and authorized analyst views of the synthetic transfer simulator."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import StringConstraints

from nexora.api.schemas import Model, Transaction
from nexora.application.errors import AppError, NotFound
from nexora.application.transfer_demo import SCENARIOS, Scenario, TransferDemo
from nexora.application.transfer_protection import (
    Action,
    ContextFact,
    Coverage,
    Decision,
    FormationProfile,
    Reason,
    RiskBand,
)
from nexora.domain.money import amount_to_str, parse_amount_minor

router = APIRouter(prefix="/api/v1/demo/transfer-checks", tags=["transfer protection"])

CUSTOMER_MESSAGES: dict[Decision, str] = {
    "ALLOW": "По доступным данным дополнительная проверка не требуется.",
    "WARN": "Есть основания проверить получателя перед продолжением.",
    "STEP_UP": "По правилам симуляции требуется дополнительная проверка.",
    "LIMITED_SIGNAL": "Данных недостаточно для оценки риска по этому переводу.",
    "UNAVAILABLE": "Проверка временно недоступна. Повторите попытку или отмените перевод.",
}


class AnalystAccessRequired(AppError):
    status_code = 403


class TransferCheckRequest(Model):
    scenario_id: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    recipient_id: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    currency: Literal["KZT"]
    amount_minor: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,37}$")]
    client_context: Literal["none"] = "none"


class ScenarioOption(Model):
    scenario_id: str
    recipient_id: str
    currency: Literal["KZT"] = "KZT"
    amount_minor: str


class TransferCheckResponse(Model):
    assessment_id: str
    decision: Decision
    risk_band: RiskBand
    coverage: Coverage
    reason_codes: tuple[Reason, ...]
    customer_message: str
    recommended_actions: tuple[Action, ...]
    snapshot_id: str | None
    policy_version: str
    simulation: Literal[True] = True


class TransferEvidenceRequest(Model):
    check: TransferCheckRequest
    assessment_id: Annotated[str, StringConstraints(min_length=36, max_length=36)]


class TransferEvidenceResponse(Model):
    assessment_id: str
    snapshot_id: str
    graph_snapshot_id: str
    graph_policy_version: str
    policy_version: str
    recipient_account_id: str
    as_of: datetime
    graph_as_of: datetime
    valid_until: datetime
    reason_codes: tuple[Reason, ...]
    formations: tuple[FormationProfile, ...]
    context: tuple[ContextFact, ...]
    transactions: tuple[Transaction, ...]
    is_repeat_recipient: bool
    simulation: Literal[True] = True


def _require_analyst(
    request: Request, token: Annotated[str | None, Header(alias="X-Nexora-Transfer-Analyst-Token")] = None
) -> None:
    expected = request.app.state.settings.transfer_analyst_token.get_secret_value()
    if len(expected) < 32 or not hmac.compare_digest((token or "").encode(), expected.encode()):
        raise AnalystAccessRequired("TRANSFER_ANALYST_ACCESS_REQUIRED", "analyst authorization is required")


def _service(request: Request, response: Response) -> TransferDemo:
    response.headers["Cache-Control"] = "no-store"
    service: TransferDemo = request.app.state.transfer_demo
    return service


Demo = Annotated[TransferDemo, Depends(_service)]


def _scenario(body: TransferCheckRequest) -> Scenario:
    scenario = SCENARIOS.get(body.scenario_id)
    if scenario is None or scenario.recipient_ref != body.recipient_id:
        raise NotFound("TRANSFER_SCENARIO_NOT_FOUND", "transfer scenario or recipient is outside demo scope")
    return scenario


@router.get("/scenarios")
def scenarios(service: Demo) -> list[ScenarioOption]:
    return [
        ScenarioOption(scenario_id=s.id, recipient_id=s.recipient_ref, amount_minor=amount_to_str(s.amount_minor))
        for s in SCENARIOS.values()
    ]


@router.post("")
def check_transfer(body: TransferCheckRequest, service: Demo) -> TransferCheckResponse:
    scenario = _scenario(body)
    result, _ = service.check(scenario, parse_amount_minor(body.amount_minor))
    return TransferCheckResponse(
        assessment_id=result.assessment_id,
        decision=result.decision,
        risk_band=result.risk_band,
        coverage=result.coverage,
        reason_codes=result.reason_codes,
        customer_message=CUSTOMER_MESSAGES[result.decision],
        recommended_actions=result.recommended_actions,
        snapshot_id=result.snapshot_id,
        policy_version=result.policy_version,
    )


@router.post("/evidence", dependencies=[Depends(_require_analyst)])
def transfer_evidence(body: TransferEvidenceRequest, service: Demo) -> TransferEvidenceResponse:
    scenario = _scenario(body.check)
    result, profile = service.check(scenario, parse_amount_minor(body.check.amount_minor))
    if result.assessment_id != body.assessment_id or profile is None:
        raise NotFound("TRANSFER_ASSESSMENT_NOT_FOUND", "assessment does not match an available demo snapshot")
    return TransferEvidenceResponse(
        assessment_id=result.assessment_id,
        snapshot_id=profile.snapshot_id,
        graph_snapshot_id=profile.graph_snapshot_id,
        graph_policy_version=profile.graph_policy_version,
        policy_version=result.policy_version,
        recipient_account_id=profile.recipient,
        as_of=scenario.as_of,
        graph_as_of=profile.as_of,
        valid_until=profile.valid_until,
        reason_codes=result.reason_codes,
        formations=profile.formations,
        context=profile.context,
        transactions=tuple(
            Transaction(
                id=tx.transaction_id,
                source_transaction_id=tx.source_transaction_id,
                sender_account_id=tx.sender,
                receiver_account_id=tx.receiver,
                amount_minor=amount_to_str(tx.amount_minor),
                currency=tx.currency,
                observed_date=tx.observed_date,
                occurred_at=tx.occurred_at,
                time_precision=tx.precision,
                status=tx.status,
                is_synthetic=True,
                ingested_at=row.known_at,
            )
            for row in profile.transactions
            for tx in (row.observed,)
        ),
        is_repeat_recipient=profile.is_repeat_recipient,
    )
