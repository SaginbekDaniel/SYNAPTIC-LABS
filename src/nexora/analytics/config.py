"""Versioned, hashed analysis configuration (detectors + risk policy)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from nexora.domain.ids import canonical_json, sha256_hex

CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"


@dataclass(frozen=True)
class AnalysisConfig:
    detectors: dict[str, Any]
    risk_policy: dict[str, Any]

    @property
    def detectors_sha256(self) -> str:
        return sha256_hex(canonical_json(self.detectors))

    @property
    def policy_sha256(self) -> str:
        return sha256_hex(canonical_json(self.risk_policy))

    @property
    def config_sha256(self) -> str:
        return sha256_hex(canonical_json({"detectors": self.detectors, "risk_policy": self.risk_policy}))

    @property
    def policy_version(self) -> str:
        return str(self.risk_policy["version"])


def load_config(config_dir: Path | None = None) -> AnalysisConfig:
    base = config_dir or CONFIG_DIR
    detectors = yaml.safe_load((base / "detectors.yaml").read_text(encoding="utf-8"))
    policy = yaml.safe_load((base / "risk_policy.yaml").read_text(encoding="utf-8"))
    return AnalysisConfig(detectors=detectors, risk_policy=policy)


@lru_cache(maxsize=1)
def default_config() -> AnalysisConfig:
    return load_config()
