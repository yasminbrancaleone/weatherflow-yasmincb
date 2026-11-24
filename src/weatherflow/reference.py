import logging
from pathlib import Path

import pandas as pd


logger = logging.getLogger(__name__)

WMO_CODES_FILE = Path(__file__).resolve().parent / "reference" / "wmo_codes.csv"
WEATHERAPI_CODES_FILE = (
    Path(__file__).resolve().parent / "reference" / "weatherapi_codes.csv"
)
_REQUIRED_COLUMNS = {"code", "description", "category"}


def _load_weather_codes(reference_file: Path, source_name: str) -> pd.DataFrame:
    """Load and validate a weather-code reference table."""
    wmo_codes = pd.read_csv(reference_file)
    missing_columns = _REQUIRED_COLUMNS.difference(wmo_codes.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"{source_name} reference is missing required column(s): {missing}."
        )

    wmo_codes["code"] = pd.to_numeric(wmo_codes["code"], errors="raise").astype("int64")
    return wmo_codes[["code", "description", "category"]].rename(
        columns={"code": "weather_code"}
    )


def load_wmo_codes(reference_file: Path = WMO_CODES_FILE) -> pd.DataFrame:
    """Load and validate the WMO weather code reference table."""
    return _load_weather_codes(reference_file, "WMO")


def load_weatherapi_codes(
    reference_file: Path = WEATHERAPI_CODES_FILE,
) -> pd.DataFrame:
    """Load and validate the WeatherAPI weather code reference table."""
    return _load_weather_codes(reference_file, "WeatherAPI")
