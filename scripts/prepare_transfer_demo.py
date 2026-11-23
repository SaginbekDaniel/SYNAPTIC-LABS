"""Rebuild the versioned synthetic snapshots delivered with the transfer demo."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from nexora.analytics.config import default_config
from nexora.application.transfer_demo import DEMO_END, PROFILE_PATH, REPLAY_END, SCENARIOS
from nexora.application.transfer_protection import ContextFact, TimedTransfer
from nexora.application.transfer_snapshot import prepare_profile
from nexora.domain.ids import transaction_uuid
from nexora.domain.transfers import ObservedTransfer


def demo_row(
    recipient: str,
    name: str,
    sender: str,
    receiver: str,
    when: datetime,
    amount: int,
    *,
    known_at: datetime | None = None,
) -> TimedTransfer:
    return TimedTransfer(
        observed=ObservedTransfer(
            transaction_uuid(recipient, "transfer-demo", name),
            name,
            sender,
            receiver,
            amount,
            "KZT",
            when.date(),
            when,
            "timestamp",
        ),
        known_at=known_at or when,
    )


def build_profiles() -> dict[str, object]:
    profiles: dict[str, object] = {}
    for scenario in SCENARIOS.values():
        if scenario.failure:
            continue
        recipient = scenario.recipient_id
        context: tuple[ContextFact, ...] = ()
        history = tuple(
            demo_row(
                recipient, f"repeat-{day}", scenario.sender_id, recipient, DEMO_END - timedelta(days=day), 1_500_000
            )
            for day in (25, 12, 4)
        )
        if scenario.id == "limited":
            history = history[-1:]
        if scenario.id in {"mule", "review", "merchant", "replay_early", "replay_late"}:
            when = DEMO_END - timedelta(days=2)
            replay = recipient == "demo-replay"
            late_import = REPLAY_END - timedelta(days=1) if replay else None
            feeder_rows = tuple(
                demo_row(
                    recipient, f"deposit-{index}", f"source-{index}", recipient, when, 4_000_000, known_at=late_import
                )
                for index in range(1, 5)
            )
            onward = demo_row(
                recipient, "onward", recipient, "payout", when + timedelta(days=1), 16_000_000, known_at=late_import
            )
            history = (*history, *feeder_rows, onward) if replay else (*feeder_rows, onward)
            if scenario.id == "merchant":
                payouts = tuple(
                    demo_row(
                        recipient,
                        f"merchant-payout-{i}",
                        recipient,
                        f"settlement-{i}",
                        when + timedelta(days=1),
                        4_000_000,
                    )
                    for i in range(1, 5)
                )
                history = (*feeder_rows, *payouts)
                context = (
                    ContextFact(
                        source_ref="demo-settlement-register",
                        kind="MERCHANT_SETTLEMENT",
                        recipient=recipient,
                        occurred_at=when + timedelta(days=1),
                        known_at=when + timedelta(days=1),
                        transaction_ids=tuple(row.observed.transaction_id for row in history),
                    ),
                )
            if scenario.id == "review" or replay:
                context = (
                    ContextFact(
                        source_ref="demo-independent-incident-register",
                        kind="CONFIRMED_REPORT",
                        recipient=recipient,
                        occurred_at=when,
                        known_at=late_import or when,
                    ),
                )
        profile = prepare_profile(scenario.intent(scenario.amount_minor), history, context, default_config())
        profiles[scenario.id] = profile.model_dump(mode="json")
    return profiles


def main(path: Path = PROFILE_PATH) -> None:
    path.write_text(json.dumps(build_profiles(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
