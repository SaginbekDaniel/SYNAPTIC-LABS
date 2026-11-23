"""Server-owned transfer scenarios and read-only precomputed recipient snapshots."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from nexora.analytics.config import CONFIG_DIR
from nexora.application.transfer_protection import Failure, Outcome, Policy, RecipientProfile, TransferIntent, assess

log = logging.getLogger(__name__)
PROFILE_PATH = Path(__file__).with_name("transfer_demo_profiles.json")
DEMO_END = datetime(2026, 10, 20, 12, tzinfo=UTC)
REPLAY_END = datetime(2026, 10, 23, 12, tzinfo=UTC)


@dataclass(frozen=True)
class Scenario:
    id: str
    sender_id: str
    recipient_id: str
    amount_minor: int
    as_of: datetime = DEMO_END
    failure: Failure | None = None

    @property
    def recipient_ref(self) -> str:
        return f"recipient-{self.recipient_id.removeprefix('demo-')}"

    def intent(self, amount_minor: int) -> TransferIntent:
        return TransferIntent(self.id, self.sender_id, self.recipient_id, self.as_of, amount_minor)


SCENARIOS = {
    s.id: s
    for s in (
        Scenario("regular", "demo-sender", "demo-regular", 1_800_000),
        Scenario("mule", "demo-sender", "demo-mule", 15_000_000),
        Scenario("merchant", "demo-sender", "demo-merchant", 24_900_000),
        Scenario("limited", "demo-sender", "demo-limited", 4_500_000),
        Scenario("review", "demo-sender", "demo-review", 12_500_000),
        Scenario("replay_early", "demo-sender", "demo-replay", 9_800_000),
        Scenario("replay_late", "demo-sender", "demo-replay", 9_800_000, as_of=REPLAY_END),
        Scenario("timeout", "demo-sender", "demo-timeout", 2_700_000, failure="TIMEOUT"),
    )
}


def load_policy() -> Policy:
    with (CONFIG_DIR / "transfer_protection.toml").open("rb") as config:
        return Policy(**tomllib.load(config))


def load_profiles(path: Path) -> dict[str, RecipientProfile] | None:
    try:
        return TypeAdapter(dict[str, RecipientProfile]).validate_json(path.read_bytes())
    except (OSError, ValueError):
        log.error("Transfer protection profile catalog is unavailable or invalid")
        return None


@dataclass(frozen=True)
class TransferDemo:
    policy: Policy | None
    profiles: dict[str, RecipientProfile] | None
    enabled: bool
    graph_config_sha256: str

    def check(self, scenario: Scenario, amount_minor: int) -> tuple[Outcome, RecipientProfile | None]:
        profile = self.profiles.get(scenario.id) if self.profiles is not None else None
        failure = scenario.failure
        if not self.enabled:
            failure = "FEATURE_DISABLED"
        elif self.policy is None or (
            failure is None
            and (
                self.profiles is None
                or (profile is not None and profile.graph_config_sha256 != self.graph_config_sha256)
            )
        ):
            failure = "DEPENDENCY_FAILURE"
        policy = self.policy or Policy(version="unavailable", warn_with_confirmed_report_alone=False)
        outcome = assess(scenario.intent(amount_minor), profile, policy, failure=failure)
        return outcome, profile if outcome.snapshot_id else None
