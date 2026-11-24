"""Tests for WeatherFlow data quality validation."""

import pandas as pd
import pytest

from weatherflow.config import load_config
from weatherflow.output import write_dq_report
from weatherflow.validate import (
    DataQualityError,
    compare_source_temperatures,
    validate,
)


@pytest.fixture
def clean_weather_row():
    """Create one valid weather record for DQ tests."""
    return {
        "city": "London",
        "observed_at_utc": pd.Timestamp("2026-11-17T12:00:00Z"),
        "temperature_c": 10.0,
        "feels_like_c": 11.0,
        "humidity_pct": 70,
        "precipitation_mm": 0.0,
        "wind_speed_kmh": 10.0,
        "source": "open-meteo",
    }


def complete_weather_rows(clean_weather_row):
    """Create one valid row for every configured city."""
    configured_cities = [
        "London",
        "Manchester",
        "Birmingham",
        "Edinburgh",
        "Cardiff",
    ]
    return [
        {**clean_weather_row, "city": city}
        for city in configured_cities
    ]


def test_clean_dataframe_passes_all_checks(clean_weather_row):
    """A complete valid row produces no quarantine or blocking failure."""
    dataframe = pd.DataFrame(complete_weather_rows(clean_weather_row))

    good_rows, quarantined_rows, results = validate(
        dataframe,
        load_config(),
        run_mode="incremental",
    )

    assert len(good_rows) == 5
    assert quarantined_rows.empty
    assert len(results) == 8


def test_incremental_run_requires_every_configured_city(clean_weather_row):
    """Incremental runs enforce city coverage for every observed hour."""
    dataframe = pd.DataFrame([clean_weather_row])

    with pytest.raises(
        DataQualityError,
        match="configured_city_hour_coverage: 4 failed rows",
    ):
        validate(
            dataframe,
            load_config(),
            run_mode="incremental",
        )


def test_temperature_99_is_quarantined_with_correct_reason(clean_weather_row):
    """A 99 C reading is quarantined for the temperature range check."""
    rows = complete_weather_rows(clean_weather_row)
    rows[0]["temperature_c"] = 99.0
    dataframe = pd.DataFrame(rows)

    good_rows, quarantined_rows, _ = validate(
        dataframe,
        load_config(),
        run_mode="incremental",
    )

    assert len(good_rows) == 4
    assert len(quarantined_rows) == 1
    assert (
        quarantined_rows.loc[quarantined_rows.index[0], "dq_failure_reason"]
        == "temperature_out_of_range"
    )


def test_missing_required_field_is_quarantined(clean_weather_row):
    """A missing required field is quarantined."""
    rows = complete_weather_rows(clean_weather_row)
    rows[0]["temperature_c"] = None
    dataframe = pd.DataFrame(rows)

    good_rows, quarantined_rows, _ = validate(
        dataframe,
        load_config(),
        run_mode="incremental",
    )

    assert len(good_rows) == 4
    assert len(quarantined_rows) == 1
    assert "missing_required_field" in quarantined_rows.iloc[0]["dq_failure_reason"]


@pytest.mark.parametrize(
    "humidity",
    [-1, 101],
)
def test_humidity_outside_range_is_quarantined(clean_weather_row, humidity):
    """Humidity below 0 or above 100 is quarantined."""
    rows = complete_weather_rows(clean_weather_row)
    rows[0]["humidity_pct"] = humidity
    dataframe = pd.DataFrame(rows)

    _, quarantined_rows, _ = validate(
        dataframe,
        load_config(),
        run_mode="incremental",
    )

    assert len(quarantined_rows) == 1
    assert "humidity_out_of_range" in quarantined_rows.iloc[0]["dq_failure_reason"]


@pytest.mark.parametrize(
    ("column", "reason"),
    [
        ("precipitation_mm", "negative_precipitation"),
        ("wind_speed_kmh", "negative_wind_speed"),
    ],
)
def test_negative_measurement_is_quarantined(clean_weather_row, column, reason):
    """Negative precipitation and wind readings are quarantined."""
    rows = complete_weather_rows(clean_weather_row)
    rows[0][column] = -1.0
    dataframe = pd.DataFrame(rows)

    _, quarantined_rows, _ = validate(
        dataframe,
        load_config(),
        run_mode="incremental",
    )

    assert len(quarantined_rows) == 1
    assert reason in quarantined_rows.iloc[0]["dq_failure_reason"]


def test_duplicate_city_hour_source_raises_data_quality_error(clean_weather_row):
    """A duplicate city/hour/source group blocks the run."""
    dataframe = pd.DataFrame([clean_weather_row, clean_weather_row])

    with pytest.raises(
        DataQualityError,
        match="Duplicate \\(city, observed_at_utc, source\\)",
    ):
        validate(
            dataframe,
            load_config(),
            run_mode="incremental",
        )


def test_cross_source_check_reports_count_threshold_and_worst_city(tmp_path):
    """The DQ result counts only above-threshold pairs and reports the worst."""
    open_meteo = pd.DataFrame(
        [
            {
                "city": "London",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 10.0,
            },
            {
                "city": "Cardiff",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 8.0,
            },
            {
                "city": "Manchester",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 9.0,
            },
        ]
    )
    weatherapi = pd.DataFrame(
        [
            {
                "city": "London",
                "observed_at_utc": "2026-11-17T12:45:00Z",
                "temperature_c": 13.0,
            },
            {
                "city": "Cardiff",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 13.0,
            },
            {
                "city": "Manchester",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 13.0,
            },
        ]
    )

    result = compare_source_temperatures(open_meteo, weatherapi, 3.0)
    report_path = write_dq_report(
        [result],
        tmp_path,
        good_rows=3,
        quarantined_rows=0,
    )
    report = report_path.read_text(encoding="utf-8")

    assert result.passed is False
    assert result.failed_rows == 2
    assert "2 exceeded the 3 C threshold" in result.details
    assert "worst city Cardiff (5 C difference)" in result.details
    assert "cross_source_temperature_difference" in report
    assert "worst city Cardiff (5 C difference)" in report


def test_cross_source_check_warns_when_no_city_hour_pairs_match():
    """A missing source overlap is reported as an unperformed comparison."""
    open_meteo = pd.DataFrame(
        [
            {
                "city": "London",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 10.0,
            }
        ]
    )
    weatherapi = pd.DataFrame(
        [
            {
                "city": "Cardiff",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 13.0,
            }
        ]
    )

    result = compare_source_temperatures(open_meteo, weatherapi, 3.0)

    assert result.passed is False
    assert result.failed_rows == 0
    assert "Compared 0 matching city/hour rows" in result.details


def test_cross_source_check_handles_an_empty_source():
    """A source with no normalized observations still yields a DQ warning."""
    weatherapi = pd.DataFrame(
        [
            {
                "city": "London",
                "observed_at_utc": "2026-11-17T12:00:00Z",
                "temperature_c": 13.0,
            }
        ]
    )

    result = compare_source_temperatures(pd.DataFrame(), weatherapi, 3.0)

    assert result.passed is False
    assert result.failed_rows == 0
    assert "worst city unavailable" in result.details
