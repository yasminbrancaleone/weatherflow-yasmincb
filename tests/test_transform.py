"""Tests for weather transformation functions."""

import pandas as pd
import pytest

from weatherflow.reference import load_wmo_codes
from weatherflow.transform import (
    add_derived_metrics,
    add_weather_description,
    deduplicate,
    flatten_payload,
    standardise_columns,
    transform,
)


def test_flatten_payload_returns_six_rows(london_payload):
    """Flattening the London fixture preserves all hourly rows."""
    result = flatten_payload(london_payload, "London")

    assert len(result) == 6
    assert set(result.columns) >= {
        "time",
        "temperature_2m",
        "is_day",
        "city",
    }


def test_temperature_conversion_is_correct(london_payload):
    """Temperature conversion from Celsius to Fahrenheit is accurate."""
    flattened = flatten_payload(london_payload, "London")
    standardised = standardise_columns(flattened)
    result = add_derived_metrics(
        standardised.assign(
            wind_speed_ms=standardised["wind_speed_kmh"] / 3.6,
            beaufort_scale=0,
            is_daylight=standardised["is_day"],
            category="clear",
        )
    )

    assert result["temperature_f"].iloc[0] == pytest.approx(46.58)


def test_unknown_weather_code_is_marked_unknown():
    """An unmapped WMO code receives unknown description and category."""
    dataframe = pd.DataFrame({"weather_code": [999]})

    result = add_weather_description(dataframe, load_wmo_codes())

    assert result.loc[0, "description"] == "unknown"
    assert result.loc[0, "category"] == "unknown"


def test_transform_uses_utc_and_london_timestamps(london_payload):
    """Transformation produces UTC and Europe/London observation timestamps."""
    result = transform(
        [("London", london_payload)],
        load_wmo_codes(),
    )

    assert len(result) == 6
    assert result["observed_at_utc"].dt.tz is not None
    assert str(result["observed_at_utc"].dt.tz) == "UTC"
    assert str(result["observed_at_local"].dt.tz) == "Europe/London"


def test_deduplicate_keeps_latest_row_for_city_and_hour():
    """Deduplication keeps the last record for each city and UTC hour."""
    dataframe = pd.DataFrame(
        {
            "city": ["London", "London"],
            "observed_at_utc": pd.to_datetime(
                ["2026-11-17T12:00:00Z", "2026-11-17T12:00:00Z"]
            ),
            "ingested_at_utc": [
                "2026-11-17T12:05:00Z",
                "2026-11-17T12:10:00Z",
            ],
            "temperature_c": [10.0, 11.0],
        }
    )

    result = deduplicate(dataframe)

    assert len(result) == 1
    assert result.loc[0, "temperature_c"] == 11.0
    assert result.loc[0, "ingested_at_utc"] == "2026-11-17T12:10:00Z"


@pytest.mark.parametrize(
    (
        "temperature_c",
        "wind_speed_ms",
        "beaufort_scale",
        "precipitation_mm",
        "category",
        "expected",
    ),
    [
        (10.0, 0.0, 0, 0.0, "clear", "low"),
        (10.0, 10.0, 5, 0.0, "clear", "medium"),
        (10.0, 13.0, 6, 0.0, "clear", "medium"),
        (10.0, 13.9, 7, 0.0, "clear", "high"),
        (10.0, 0.0, 0, 1.0, "clear", "medium"),
        (10.0, 0.0, 0, 4.0, "clear", "high"),
        (0.0, 0.0, 0, 0.0, "clear", "medium"),
        (-1.0, 0.0, 0, 0.0, "clear", "medium"),
        (10.0, 0.0, 0, 0.0, "snow", "high"),
        (10.0, 0.0, 0, 0.0, "storm", "high"),
    ],
)
def test_outdoor_work_risk_boundaries(
    temperature_c,
    wind_speed_ms,
    beaufort_scale,
    precipitation_mm,
    category,
    expected,
):
    """Outdoor work risk applies every rule and boundary exactly."""
    dataframe = pd.DataFrame(
        {
            "temperature_c": [temperature_c],
            "wind_speed_ms": [wind_speed_ms],
            "wind_speed_kmh": [wind_speed_ms * 3.6],
            "beaufort_scale": [beaufort_scale],
            "precipitation_mm": [precipitation_mm],
            "category": [category],
            "is_day": [True],
        }
    )

    result = add_derived_metrics(dataframe)

    assert result.loc[0, "outdoor_work_risk"] == expected
