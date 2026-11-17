"""Demonstrate quarantine and blocking data quality behavior."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from weatherflow.config import load_config
from weatherflow.output import write_quarantine
from weatherflow.validate import DataQualityError, validate


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _sample_rows() -> pd.DataFrame:
    """Create representative weather rows for the demonstration."""
    return pd.DataFrame(
        [
            {
                "city": "London",
                "observed_at_utc": pd.Timestamp("2026-11-17T12:00:00Z"),
                "temperature_c": 10.0,
                "feels_like_c": 10.0,
                "humidity_pct": 70,
                "precipitation_mm": 0.0,
                "wind_speed_kmh": 10.0,
                "source": "open-meteo",
            }
        ]
    )


def demonstrate() -> None:
    """Inject bad data and print the expected DQ outcomes."""
    config = load_config()

    high_temperature = _sample_rows()
    high_temperature.loc[0, "temperature_c"] = 99.0
    good_rows, quarantined_rows, _ = validate(
        high_temperature,
        config,
        run_mode="incremental",
    )

    with TemporaryDirectory() as directory:
        quarantine_path = write_quarantine(
            quarantined_rows,
            Path(directory),
            datetime(2026, 11, 17, 18, 30, tzinfo=timezone.utc),
        )
    logger.info(
        "High-temperature demonstration: good=%d quarantined=%d file=%s",
        len(good_rows),
        len(quarantined_rows),
        quarantine_path,
    )

    duplicate_rows = pd.concat([_sample_rows(), _sample_rows()], ignore_index=True)
    try:
        validate(duplicate_rows, config, run_mode="incremental")
    except DataQualityError as error:
        logger.warning("Duplicate demonstration correctly blocked the run: %s", error)
    else:
        raise RuntimeError("Duplicate data was not blocked.")


if __name__ == "__main__":
    demonstrate()
