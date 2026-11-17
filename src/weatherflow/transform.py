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
    return standardised


def deduplicate(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest record for each city and UTC observation timestamp."""
    return dataframe.drop_duplicates(
        subset=["city", "observed_at_utc"], keep="last"
    ).reset_index(drop=True)


def transform(raw_records: list[tuple[str, dict[str, Any]]]) -> pd.DataFrame:
    """Transform raw weather records into the canonical hourly dataset."""
    if not raw_records:
        logger.warning("No raw data available for transformation.")
        return pd.DataFrame()

    flattened = [
        flatten_payload(payload, city_name)
        for city_name, payload in raw_records
    ]
    combined = pd.concat(flattened, ignore_index=True)
    transformed = standardise_columns(combined)
    transformed["ingested_at_utc"] = datetime.now(timezone.utc).isoformat()
    transformed = deduplicate(transformed)

    logger.info("Transformed %d weather observations.", len(transformed))
    return transformed[_OUTPUT_COLUMNS]