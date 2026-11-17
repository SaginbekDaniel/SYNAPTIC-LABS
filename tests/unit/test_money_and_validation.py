import pytest

from nexora.domain.money import MoneyError, amount_to_str, parse_amount_minor, parse_currency
from nexora.ingest.csv_adapter import CsvSchemaError, read_csv_rows
from nexora.ingest.validation import parse_record, prepare_batch


@pytest.mark.parametrize("bad", [1.5, 100.0, "1.5", "1e5", "-5", "0", 0, -1, True, "", " ", None, "12,00"])
def test_amount_rejects_non_integer_minor_units(bad):
    with pytest.raises(MoneyError):
        parse_amount_minor(bad)


def test_amount_keeps_values_beyond_js_safe_integer():  # DATA-002
    big = 2**63 + 12345
    assert parse_amount_minor(str(big)) == big
    assert amount_to_str(big) == str(big)


def test_currency_validation():  # DATA-007
    assert parse_currency("KZT") == "KZT"
    for bad in ["kzt", "KZ", "KZTT", 398, None]:
        with pytest.raises(MoneyError):
            parse_currency(bad)


def _row(**over):
    base = {
        "source_transaction_id": "t1",
        "sender_account_id": "9007199254740993",
        "receiver_account_id": "A-1",
        "amount_minor": "1000",
        "currency": "KZT",
        "observed_date": "2026-07-01",
    }
    base.update(over)
    return base


def test_account_ids_are_kept_as_exact_strings():  # DATA-001 (ingest side)
    rec = parse_record(_row(), row_number=1, source_id="s", is_synthetic=True)
    assert rec.sender_account_id == "9007199254740993"  # 2^53 + 1, not representable as a JS number
    numeric = parse_record(_row(sender_account_id=9007199254740993), row_number=1, source_id="s", is_synthetic=True)
    assert getattr(numeric, "code", None) == "MISSING_ACCOUNT_ID"  # numeric types indicate lossy upstream conversion


def test_day_precision_has_no_timestamp():  # DATA-006
    rec = parse_record(_row(), row_number=1, source_id="s", is_synthetic=True)
    assert rec.time_precision == "day" and rec.occurred_at is None


def test_timestamp_requires_offset():
    issue = parse_record(_row(occurred_at="2026-07-01T10:00:00"), row_number=3, source_id="s", is_synthetic=True)
    assert issue.code == "TIMESTAMP_INVALID" and issue.row_number == 3
    rec = parse_record(_row(occurred_at="2026-07-01T10:00:00+05:00"), row_number=1, source_id="s", is_synthetic=True)
    assert rec.time_precision == "timestamp" and rec.occurred_at.utcoffset().total_seconds() == 0


def test_batch_duplicates_and_conflicts():  # DATA-004, DATA-005
    rows = [
        (1, _row()),
        (2, _row()),
        (3, _row(amount_minor="999")),
        (4, _row(source_transaction_id="t2", currency="xx")),
    ]
    records, report = prepare_batch(rows, source_id="s", is_synthetic=True)
    assert len(records) == 1 and report.accepted == 1
    assert report.duplicated_identical == 1
    assert report.quarantined == 2
    assert report.error_codes == {"CONFLICTING_TRANSACTION_DUPLICATE": 1, "CURRENCY_INVALID": 1}
    # The report must not echo raw payload values.
    assert "999" not in str(report.as_dict()["examples"])


def test_csv_schema_errors_are_fatal():
    with pytest.raises(CsvSchemaError) as e:
        read_csv_rows(b"sender_account_id,amount_minor\n1,2\n")
    assert e.value.code == "CSV_SCHEMA_INVALID"


def test_csv_derived_ids_are_stable_and_keep_genuine_repeats():
    content = (
        b"sender_account_id,receiver_account_id,amount_minor,currency,observed_date\n"
        b"A,B,100,KZT,2026-07-01\nA,B,100,KZT,2026-07-01\nB,C,50,KZT,2026-07-02\n"
    )
    rows1, digest1 = read_csv_rows(content)
    rows2, digest2 = read_csv_rows(content)
    ids = [r["source_transaction_id"] for _, r in rows1]
    assert ids == [r["source_transaction_id"] for _, r in rows2] and digest1 == digest2
    assert len(set(ids)) == 3  # two equal-looking transfers are both kept
