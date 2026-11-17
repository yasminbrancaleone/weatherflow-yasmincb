from datetime import datetime, timezone
import logging
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)


def transform(raw: list[tuple[str, dict[str, Any]]]) -> pd.DataFrame:
    """Flatten weather payloads, standardize columns, and deduplicate observations."""
    dataframes = []
    ingested_at = datetime.now(timezone.utc).isoformat()

    for city_name, payload in raw:
        dataframe = pd.DataFrame(payload["hourly"])
        dataframe["city"] = city_name
        dataframes.append(dataframe)

    if not dataframes:
        logger.warning("No raw data available for transformation.")
        return pd.DataFrame()

    combined = pd.concat(dataframes, ignore_index=True)
    combined = combined.rename(
        columns={
            "time": "observed_at",
            "temperature_2m": "temperature_c",
            "apparent_temperature": "feels_like_c",
            "relative_humidity_2m": "humidity_pct",
            "precipitation": "precipitation_mm",
            "wind_speed_10m": "wind_speed_kmh",
            "weather_code": "weather_code",
        }
    )
    combined["observed_at"] = pd.to_datetime(
        combined["observed_at"], format="mixed"
    )
    combined["ingested_at_utc"] = ingested_at
    combined = combined.drop_duplicates(
        subset=["city", "observed_at"], keep="last"
    )

    columns_order = [
        "city",
        "observed_at",
        "temperature_c",
        "feels_like_c",
        "humidity_pct",
        "precipitation_mm",
        "wind_speed_kmh",
        "weather_code",
        "ingested_at_utc",
    ]
    transformed = combined[columns_order]
    logger.info("Transformed %d weather observations.", len(transformed))
    return transformed