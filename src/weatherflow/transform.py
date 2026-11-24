from datetime import datetime, timezone
import logging
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)


_COLUMN_RENAMES = {
    "time": "observed_at_utc",
    "temperature_2m": "temperature_c",
    "apparent_temperature": "feels_like_c",
    "relative_humidity_2m": "humidity_pct",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "weather_code": "weather_code",
}
_OUTPUT_COLUMNS = [
    "city",
    "observed_at_utc",
    "observed_at_local",
    "temperature_c",
    "feels_like_c",
    "humidity_pct",
    "precipitation_mm",
    "wind_speed_kmh",
    "weather_code",
    "description",
    "category",
    "temperature_f",
    "wind_speed_ms",
    "beaufort_scale",
    "is_daylight",
    "outdoor_work_risk",
    "ingested_at_utc",
]


def flatten_payload(payload: dict[str, Any], city: str) -> pd.DataFrame:
    """Flatten one hourly API payload and add its city name."""
    dataframe = pd.DataFrame(payload["hourly"])
    dataframe["city"] = city
    return dataframe


def standardise_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Rename weather columns and derive UTC and local timestamps."""
    standardised = dataframe.rename(
        columns=_COLUMN_RENAMES
    ).copy()
    standardised["observed_at_utc"] = pd.to_datetime(
        standardised["observed_at_utc"], format="mixed", utc=True
    )
    standardised["observed_at_local"] = standardised[
        "observed_at_utc"
    ].dt.tz_convert("Europe/London")
    standardised["is_day"] = standardised["is_day"].astype("boolean")
    return standardised


def normalise_open_meteo_payload(
    payload: dict[str, Any],
    city: str,
) -> pd.DataFrame:
    """Convert one Open-Meteo payload to the shared hourly column format."""
    return standardise_columns(flatten_payload(payload, city))


def normalise_weatherapi_payload(
    payload: dict[str, Any],
    city: str,
) -> pd.DataFrame:
    """Convert one WeatherAPI payload to the shared hourly column format."""
    observations = [
        hour
        for forecast_day in payload["forecast"]["forecastday"]
        for hour in forecast_day["hour"]
    ]
    normalized = pd.DataFrame(
        {
            "city": city,
            "observed_at_utc": pd.to_datetime(
                [hour["time_epoch"] for hour in observations],
                unit="s",
                utc=True,
            ),
            "temperature_c": [hour["temp_c"] for hour in observations],
            "feels_like_c": [hour["feelslike_c"] for hour in observations],
            "humidity_pct": [hour["humidity"] for hour in observations],
            "precipitation_mm": [hour["precip_mm"] for hour in observations],
            "wind_speed_kmh": [hour["wind_kph"] for hour in observations],
            "weather_code": [
                hour["condition"]["code"] for hour in observations
            ],
            "is_day": [hour["is_day"] for hour in observations],
        }
    )
    normalized["observed_at_local"] = normalized[
        "observed_at_utc"
    ].dt.tz_convert("Europe/London")
    normalized["is_day"] = normalized["is_day"].astype("boolean")
    return normalized


def normalise_records(
    raw_records: list[tuple[str, dict[str, Any]]],
    source: str,
) -> pd.DataFrame:
    """Normalise raw records for one source into the shared column format."""
    if not raw_records:
        return pd.DataFrame()

    normalise = (
        normalise_weatherapi_payload
        if source == "weatherapi_forecast"
        else normalise_open_meteo_payload
    )
    normalized_records = [
        normalise(payload, city_name)
        for city_name, payload in raw_records
    ]
    return pd.concat(normalized_records, ignore_index=True)


def deduplicate(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest record for each city and UTC observation timestamp."""
    return dataframe.drop_duplicates(
        subset=["city", "observed_at_utc"], keep="last"
    ).reset_index(drop=True)


def add_weather_description(
    dataframe: pd.DataFrame, wmo_codes: pd.DataFrame
) -> pd.DataFrame:
    """Join WMO descriptions and categories, using unknown for unmapped codes."""
    enriched = dataframe.merge(wmo_codes, on="weather_code", how="left")
    enriched["description"] = enriched["description"].fillna("unknown")
    enriched["category"] = enriched["category"].fillna("unknown")
    return enriched


def add_derived_metrics(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add unit conversions, Beaufort scale, daylight, and work risk metrics."""
    derived = dataframe.copy()
    derived["temperature_f"] = derived["temperature_c"] * 9 / 5 + 32
    derived["wind_speed_ms"] = derived["wind_speed_kmh"] / 3.6
    derived["beaufort_scale"] = pd.cut(
        derived["wind_speed_ms"].round(10),
        bins=[
            float("-inf"),
            0.5,
            1.6,
            3.4,
            5.5,
            8.0,
            10.8,
            13.9,
            17.2,
            20.8,
            24.5,
            28.5,
            32.7,
            float("inf"),
        ],
        labels=list(range(13)),
        right=False,
    ).astype("Int64")
    derived["is_daylight"] = derived["is_day"]

    high_risk = (
        derived["beaufort_scale"].ge(7).fillna(False)
        | derived["category"].isin(["storm", "snow"])
        | derived["precipitation_mm"].ge(4).fillna(False)
    )
    medium_risk = (
        derived["beaufort_scale"].ge(5).fillna(False)
        | derived["precipitation_mm"].ge(1).fillna(False)
        | derived["temperature_c"].le(0).fillna(False)
    )
    derived["outdoor_work_risk"] = "low"
    derived.loc[medium_risk, "outdoor_work_risk"] = "medium"
    derived.loc[high_risk, "outdoor_work_risk"] = "high"
    return derived


def transform(
    raw_records: list[tuple[str, dict[str, Any]]],
    weather_codes: pd.DataFrame,
    source: str = "open_meteo_forecast",
) -> pd.DataFrame:
    """Transform raw weather records into the canonical hourly dataset."""
    if not raw_records:
        logger.warning("No raw data available for transformation.")
        return pd.DataFrame()

    transformed = normalise_records(raw_records, source)
    transformed = add_weather_description(transformed, weather_codes)
    transformed = add_derived_metrics(transformed)
    transformed["ingested_at_utc"] = datetime.now(timezone.utc).isoformat()
    transformed = deduplicate(transformed)

    logger.info("Transformed %d weather observations.", len(transformed))
    return transformed[_OUTPUT_COLUMNS]