from __future__ import annotations

from nexora.evaluation.transfer_protection import _rates, evaluate


def test_confusion_matrix_keeps_abstentions_in_the_denominator() -> None:
    result = _rates(
        [
            (True, "WARN", 1_000_000),
            (True, "LIMITED_SIGNAL", 2_000_000),
            (False, "STEP_UP", 3_000_000),
            (False, "UNAVAILABLE", 4_000_000),
            (False, "ALLOW", 5_000_000),
        ]
    )
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (1, 1, 2, 1)
    assert result["recall"] == 0.5
    assert result["precision"] == 0.5
    assert result["false_warnings_per_1000_legitimate"] == 1000 / 3
    assert result["limited_signal_rate"] == result["unavailable_rate"] == 0.2
    assert result["latency_ms"] == {"p50": 3.0, "p95": 5.0, "p99": 5.0}


def test_holdout_replays_the_same_inputs_and_predictions() -> None:
    first, second = evaluate(), evaluate()
    assert first["dataset_sha256"] == second["dataset_sha256"]
    assert first["snapshot_manifest_sha256"] == second["snapshot_manifest_sha256"]
    assert first["policy_decisions_by_stratum"] == second["policy_decisions_by_stratum"]
    for name, stats in first["results"].items():
        assert stats["tp"] + stats["fn"] == first["fraud_count"]
        assert stats["fp"] + stats["tn"] == first["legitimate_count"]
        assert stats["decisions"] == second["results"][name]["decisions"]
