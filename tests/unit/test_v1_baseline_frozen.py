"""The v1 engine stays reproducible so benchmark regressions remain measurable.

``configs/v1`` is the frozen baseline configuration. Any code change that alters its output
on the reference input breaks comparability with the recorded baseline benchmark run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from nexora.analytics.config import CONFIG_DIR, load_config
from nexora.analytics.pipeline import run_analysis

V1_GOLDEN = "051d7156022052580728a1d38f16dc4c138b21acf46565293f75db46c977277b"


def _trace_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[2] / "scripts" / "trace_v1_false_positives.py"
    spec = importlib.util.spec_from_file_location("trace_v1", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v1_engine_output_is_frozen() -> None:
    trace = _trace_module()
    ds, transfers = trace.load("demo-v1", 2026)
    out = run_analysis(
        dataset_id="demo", transfers=transfers, contract=ds.coverage_contract, config=load_config(CONFIG_DIR / "v1")
    )
    assert len(out.assessments) == 70
    assert trace.assessments_fingerprint(out) == V1_GOLDEN
