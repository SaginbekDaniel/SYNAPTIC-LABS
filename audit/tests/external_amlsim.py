"""Measure alert-account hits on the official IBM AMLSim toy sample."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from nexora.analytics.config import default_config
from nexora.analytics.pipeline import run_analysis
from nexora.domain.transfers import ObservedTransfer

SOURCE_COMMIT = "7338a4bcb1af9bcfea2201ad7daccfe2a4d569ca"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    tx_path = args.sample_dir / "tx.csv"
    alert_path = args.sample_dir / "alerts.csv"
    with tx_path.open(newline="") as file:
        transfers = [
            ObservedTransfer(
                row["TXN_ID"],
                row["TXN_ID"],
                row["ACCOUNT_ID"],
                row["COUNTER_PARTY_ACCOUNT_NUM"],
                int(Decimal(row["TXN_AMOUNT_ORIG"]) * 100),
                "USD",
                date(2017, 1, 1) + timedelta(days=int(row["start"]) - 1),
                None,
                "day",
            )
            for row in csv.DictReader(file)
        ]
    with alert_path.open(newline="") as file:
        labels = {row["ACCOUNT_ID"] for row in csv.DictReader(file)}
    config = default_config()
    output = run_analysis(
        dataset_id="ibm-amlsim-sample", transfers=transfers, contract={"declared_complete": False}, config=config
    )
    by_formation = {row.id: row for row in output.formations}
    subjects = {
        by_formation[item.formation_id].subject_account_id
        for item in output.assessments
        if item.band in {"medium", "high", "critical"}
    }
    accounts = {account for row in transfers for account in (row.sender, row.receiver)}
    scoped_labels = accounts & labels
    matches = subjects & scoped_labels
    summary = {
        "upstream_repo": "https://github.com/IBM/AMLSim",
        "upstream_commit": SOURCE_COMMIT,
        "source_hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (tx_path, alert_path)},
        "rows": len(transfers),
        "accounts": len(accounts),
        "labelled_alert_accounts": sorted(labels),
        "labelled_accounts_present": sorted(scoped_labels),
        "flagged_account_subjects": sorted(subjects),
        "labelled_alert_subject_hit_rate": len(matches) / len(scoped_labels) if scoped_labels else None,
        "formations": len(output.formations),
        "min_amount_minor": min(row.amount_minor for row in transfers),
        "max_amount_minor": max(row.amount_minor for row in transfers),
        "day_precision": True,
        "assumed_currency_for_units": "USD",
        "notes": [
            "Toy sample, account alert labels only. Other accounts are unlabeled.",
            "Sample records are interpreted as directed edges from account to counterparty.",
            "No rescaling, synthetic day index anchored to an arbitrary date, no invented timestamps.",
            "Cash rows lack a counterparty account and are excluded.",
        ],
    }
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
