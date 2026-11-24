from pathlib import Path
import logging
from typing import Any

import yaml


logger = logging.getLogger(__name__)


CONFIG_FILE = Path(__file__).resolve().parents[2] / "config.yaml"

_REQUIRED_API_KEYS = (
    "forecast_url",
    "archive_url",
    "timeout_seconds",
    "max_retries",
    "hourly_variables",
    "timezone",
)
_REQUIRED_CITY_KEYS = ("name", "country", "latitude", "longitude")
_REQUIRED_PATH_KEYS = (
    "raw_dir",
    "processed_dir",
    "quarantine_dir",
    "dq_report_dir",
    "database",
)


class ConfigurationError(ValueError):
    """Raised when the pipeline configuration is missing or invalid."""


def _require_mapping(value: Any, section_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"Configuration section '{section_name}' must be a mapping."
        )
    return value


def _require_keys(
    section: dict[str, Any], required_keys: tuple[str, ...], section_name: str
) -> None:
    missing_keys = [key for key in required_keys if key not in section]
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise ConfigurationError(
            f"Missing required configuration key(s) in '{section_name}': {missing}."
        )


def load_config(config_file: Path = CONFIG_FILE) -> dict[str, Any]:
    """Load, validate, and normalize the pipeline configuration."""
    config_path = config_file.resolve()

    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except FileNotFoundError as error:
        raise ConfigurationError(
            f"Configuration file not found: {config_path}"
        ) from error
    except yaml.YAMLError as error:
        raise ConfigurationError(
            f"Invalid YAML in configuration file: {config_path}"
        ) from error

    config = _require_mapping(raw_config, "root")
    _require_keys(config, ("api", "cities", "paths"), "root")

    api_config = _require_mapping(config["api"], "api")
    _require_keys(api_config, _REQUIRED_API_KEYS, "api")

    cities = config["cities"]
    if not isinstance(cities, list) or not cities:
        raise ConfigurationError("Configuration key 'cities' must be a non-empty list.")
    for index, city in enumerate(cities):
        city_config = _require_mapping(city, f"cities[{index}]")
        _require_keys(city_config, _REQUIRED_CITY_KEYS, f"cities[{index}]")

    dim_date = _require_mapping(config.get("dim_date"), "dim_date")
    _require_keys(dim_date, ("start", "end"), "dim_date")

    dq = _require_mapping(config.get("dq"), "dq")
    _require_keys(
        dq,
        (
            "temperature_min_c",
            "temperature_max_c",
            "humidity_min_pct",
            "humidity_max_pct",
            "precipitation_min_mm",
            "wind_speed_min_kmh",
            "feels_like_tolerance_c",
            "timeliness_hours",
        ),
        "dq",
    )

    paths_config = _require_mapping(config["paths"], "paths")
    if not paths_config:
        raise ConfigurationError("Configuration section 'paths' must not be empty.")
    _require_keys(paths_config, _REQUIRED_PATH_KEYS, "paths")

    absolute_paths: dict[str, Path] = {}
    for key, value in paths_config.items():
        if not isinstance(value, str) or not value:
            raise ConfigurationError(
                f"Configuration path '{key}' must be a non-empty string."
            )
        absolute_paths[key] = (config_path.parent / value).resolve()

    config["paths"] = absolute_paths
    return config
