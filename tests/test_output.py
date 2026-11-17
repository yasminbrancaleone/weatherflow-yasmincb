"""Tests for processed and data quality output writers."""

from datetime import datetime, timezone

import pandas as pd

from weatherflow.output import (
    write_dq_report,
    write_processed_parquet,
    write_quarantine,
)
from weatherflow.validate import CheckResult


def test_write_processed_parquet_creates_partition(tmp_path):
    """Processed output is written to a date-partitioned Parquet file."""
    dataframe = pd.DataFrame({"city": ["London"], "temperature_c": [10.0]})
    run_at = datetime(2026, 11, 17, 12, 30, tzinfo=timezone.utc)

    output = write_processed_parquet(dataframe, tmp_path, run_at)

    assert output.exists()
    assert output.parent.name == "run_date=2026-11-17"
    assert output.name == "part-20261117T123000Z.parquet"
    assert pd.read_parquet(output).equals(dataframe)


def test_write_quarantine_returns_none_for_empty_dataframe(tmp_path):
    """An empty quarantine DataFrame does not create a file."""
    output = write_quarantine(pd.DataFrame(), tmp_path)

    assert output is None


def test_write_quarantine_creates_csv_with_reason(tmp_path):
    """Quarantined rows are written with their failure reasons."""
    dataframe = pd.DataFrame(
        {
            "city": ["London"],
            "dq_failure_reason": ["temperature_out_of_range"],
        }
    )
    run_at = datetime(2026, 11, 17, 12, 30, tzinfo=timezone.utc)

    output = write_quarantine(dataframe, tmp_path, run_at)

    assert output is not None
    assert output.exists()
    assert output.parent.name == "run_date=2026-11-17"
    assert pd.read_csv(output).loc[0, "dq_failure_reason"] == "temperature_out_of_range"


def test_write_dq_report_creates_markdown_summary(tmp_path):
    """The DQ report includes check status and row counts."""
    results = [
        CheckResult(
            "temperature_range",
            "validity",
            "quarantine",
            False,
            1,
            "99 C is out of range",
        )
    ]
    run_at = datetime(2026, 11, 17, 12, 30, tzinfo=timezone.utc)

    output = write_dq_report(results, tmp_path, 5, 1, run_at)
    report = output.read_text(encoding="utf-8")

    assert output.exists()
    assert "- **Good rows:** 5" in report
    assert "- **Quarantined rows:** 1" in report
    assert "| temperature_range | validity | quarantine | FAIL | 1 |" in report
