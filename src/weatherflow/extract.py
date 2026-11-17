from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any

import requests


logger = logging.getLogger(__name__)


def _is_retryable(error: requests.RequestException) -> bool:
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(error, requests.HTTPError):
        return error.response is not None and error.response.status_code >= 500
    return False


def _fetch_payload(
    city: dict[str, Any], api_config: dict[str, Any]
) -> dict[str, Any]:
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": ",".join(api_config["hourly_variables"]),
        "past_days": api_config["past_days"],
        "forecast_days": api_config["forecast_days"],
        "timezone": api_config["timezone"],
    }
    max_retries = api_config["max_retries"]

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                api_config["forecast_url"],
                params=params,
                timeout=api_config["timeout_seconds"],
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            if not _is_retryable(error) or attempt == max_retries:
                logger.error("Failed extracting %s: %s", city["name"], error)
                raise

            delay = 2**attempt
            logger.warning(
                "Retrying extraction for %s after attempt %d/%d: %s; "
                "waiting %d second(s)",
                city["name"],
                attempt + 1,
                max_retries + 1,
                error,
                delay,
            )
            time.sleep(delay)

    raise RuntimeError("Request retry loop ended unexpectedly.")


def extract(config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Fetch and save raw weather payloads for every configured city."""
    api_config = config["api"]
    raw_directory = Path(config["paths"]["raw_dir"])
    now = datetime.now(timezone.utc)
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    folder_path = raw_directory / date_folder
    folder_path.mkdir(parents=True, exist_ok=True)

    raw_payloads: list[tuple[str, dict[str, Any]]] = []
    for city in config["cities"]:
        payload = _fetch_payload(city, api_config)

        clean_name = city["name"].lower().replace(" ", "_")
        file_path = folder_path / f"{clean_name}_{timestamp}.json"
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

        raw_payloads.append((city["name"], payload))
        logger.info("Saved raw payload for %s", city["name"])

    return raw_payloads
