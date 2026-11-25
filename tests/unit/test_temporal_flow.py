from nexora.analytics.temporal.flow import layered_flow
from tests.helpers import tx

KW = {"max_lag_days": 7, "min_compatible_fraction": "0.5", "max_transfers": 600}


def test_time_respecting_chain_supported():  # TEMP-001
    r = layered_flow([[tx("1", "A", "B", 100, 0)], [tx("2", "B", "C", 95, 1)], [tx("3", "C", "D", 90, 3)]], **KW)
    assert r.status == "supported"
    assert r.strict_compatible_minor == 90
    assert set(r.supporting_transaction_ids) == {"1", "2", "3"}
    assert r.lag_days_min == 1 and r.lag_days_max == 2
    assert r.lag_seconds_min is None  # day-only data never yields elapsed seconds (DATA-006)


def test_reverse_chronology_contradicted():  # TEMP-002
    r = layered_flow([[tx("1", "A", "B", 100, 5)], [tx("2", "B", "C", 95, 1)]], **KW)
    assert r.status == "contradicted" and r.possible_compatible_minor == 0
    assert "chronology_rules_out_flow" in r.limitations


def test_same_day_is_ambiguous_not_ordered():  # TEMP-003
    r = layered_flow([[tx("1", "A", "B", 100, 2)], [tx("2", "B", "C", 95, 2)]], **KW)
    assert r.status == "possible_ambiguous"
    assert r.strict_compatible_minor == 0 and r.possible_compatible_minor == 95
    assert r.uncertain_transition_count == 1
    assert "same_day_order_unresolved" in r.limitations


def test_capacity_bound_incoming_100_outgoing_130():  # TEMP-004
    r = layered_flow([[tx("1", "A", "B", 100, 0)], [tx("2", "B", "C", 70, 1), tx("3", "B", "D", 60, 2)]], **KW)
    assert r.strict_compatible_minor == 100  # never more than what came in


def test_no_phantom_reuse_of_incoming_value():  # TEMP-005 / spec §10.6 case 6
    r = layered_flow(
        [
            [tx("i1", "A", "B", 50, 0), tx("i2", "X", "B", 50, 0)],
            [tx("o1", "B", "C", 80, 1), tx("o2", "B", "C", 80, 2)],
        ],
        **KW,
    )
    assert r.strict_compatible_minor == 100
    dup = layered_flow([[tx("1", "A", "B", 100, 0), tx("1", "A", "B", 100, 0)], [tx("2", "B", "C", 500, 1)]], **KW)
    assert dup.strict_compatible_minor == 100  # a duplicated record adds no capacity


def test_outgoing_before_incoming_does_not_count():
    r = layered_flow([[tx("1", "A", "B", 100, 3)], [tx("2", "B", "C", 100, 1), tx("3", "B", "C", 30, 4)]], **KW)
    assert r.strict_compatible_minor == 30 and r.status == "contradicted"
    assert "insufficient_compatible_amount" in r.limitations


def test_lag_window_is_enforced():
    r = layered_flow([[tx("1", "A", "B", 100, 0)], [tx("2", "B", "C", 100, 20)]], **KW)
    assert r.status == "contradicted"


def test_missing_leg_and_currency_mix_unavailable():  # spec §10.6 cases 8, 9
    assert layered_flow([[tx("1", "A", "B", 100, 0)], []], **KW).status == "unavailable"
    mix = layered_flow([[tx("1", "A", "B", 100, 0)], [tx("2", "B", "C", 100, 1, currency="USD")]], **KW)
    assert mix.status == "unavailable" and mix.limitations == ("currency_mix",)


def test_reversed_transfers_carry_no_capacity():  # spec §10.6 case 7
    r = layered_flow([[tx("1", "A", "B", 100, 0, status="reversed")], [tx("2", "B", "C", 100, 1)]], **KW)
    assert r.status == "unavailable"


def test_timestamps_give_exact_lags_and_strict_order():
    r = layered_flow([[tx("1", "A", "B", 100, 0, seconds=3600)], [tx("2", "B", "C", 100, 0, seconds=7200)]], **KW)
    assert r.status == "supported" and r.precision == "timestamp"
    assert r.lag_seconds_min == 3600 and r.lag_days_min == 0
    same = layered_flow([[tx("1", "A", "B", 100, 0, seconds=60)], [tx("2", "B", "C", 100, 0, seconds=60)]], **KW)
    assert same.status == "possible_ambiguous"


def test_budget_exceeded_is_explicit():  # spec §10.6 case 10
    many = [tx(f"i{i}", f"S{i}", "B", 10, 0) for i in range(20)]
    r = layered_flow([many, [tx("o", "B", "C", 100, 1)]], **{**KW, "max_transfers": 5})
    assert r.status == "unavailable" and r.limitations == ("flow_budget_exceeded",)


def test_temporal_index_keeps_boundary_and_reports_effective_coverage():
    incoming = [tx("in", "A", "B", 100, 0)]
    outgoing = [
        *[tx(f"noise-{i}", f"W{i}", "C", 100, 4) for i in range(150)],
        tx("exact-window", "B", "C", 80, 7),
        tx("outside-window", "B", "C", 100, 8),
    ]
    result = layered_flow([incoming, outgoing], **KW)
    assert result.strict_compatible_minor == 80
    assert result.supporting_transaction_ids == ("exact-window", "in")
    assert result.eligible_transfers == result.processed_transfers == 153

    result = layered_flow([incoming, outgoing], **{**KW, "max_transfers": 152})
    assert result.eligible_transfers == 153 and result.processed_transfers == 0
    assert result.limitations == ("flow_budget_exceeded",)
