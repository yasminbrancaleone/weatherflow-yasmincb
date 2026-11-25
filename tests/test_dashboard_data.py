import pandas as pd

from weatherflow.dashboard_data import (
    add_london_time,
    flag_source_disagreements,
    load_latest_dq_summary,
)


def test_add_london_time_converts_utc_for_display():
    """UTC observations gain a Europe/London display timestamp."""
    dataframe = pd.DataFrame(
        {"observed_at_utc": [pd.Timestamp("2026-07-01T12:00:00Z")]}
    )

    result = add_london_time(dataframe)

    assert str(result.loc[0, "observed_at_london"]) == (
        "2026-07-01 13:00:00+01:00"
    )
    assert str(result.loc[0, "observed_at_utc"]) == (
        "2026-07-01 12:00:00+00:00"
    )


def test_flag_source_disagreements_uses_strict_configured_threshold():
    """Only paired readings differing by more than the threshold are flagged."""
    dataframe = pd.DataFrame(
        {
            "observed_at_utc": [
                pd.Timestamp("2026-07-01T12:00:00Z"),
                pd.Timestamp("2026-07-01T13:00:00Z"),
            ],
            "open_meteo_temperature_c": [10.0, 15.1],
            "weatherapi_temperature_c": [13.0, 12.0],
        }
    )

    result = flag_source_disagreements(dataframe, threshold_c=3.0)

    assert result["disagreement"].tolist() == [False, True]


def test_load_latest_dq_summary_reads_check_and_quarantine_counts(tmp_path):
    """The dashboard extracts the latest DQ report counts."""
    (tmp_path / "20261125T100000Z-open_meteo_forecast.md").write_text(
        "# Data Quality Report\n\n"
        "- **Good rows:** 10\n"
        "- **Quarantined rows:** 2\n\n"
        "| Check | Dimension | Severity | Status | Failed rows | Details |\n"
        "|---|---|---|---|---:|---|\n"
        "| required | completeness | error | PASS | 0 | OK |\n"
        "| range | validity | error | FAIL | 2 | Outside limits |\n",
        encoding="utf-8",
    )

    assert load_latest_dq_summary(tmp_path) == {
        "good_rows": 10,
        "quarantined_rows": 2,
        "passed_checks": 1,
        "failed_checks": 1,
    }
