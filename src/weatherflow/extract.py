from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any

import requests


logger = logging.getLogger(__name__)


def iter_archive_chunks(
    start_date: date,
    end_date: date,
    chunk_days: int = 7,
) -> list[tuple[date, date]]:
    """Split an inclusive date range into chunks of at most seven days."""
    if chunk_days < 1:
        raise ValueError("chunk_days must be at least 1.")
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")

    chunks = []
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=chunk_days - 1), end_date)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks


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


def _fetch_archive_payload(
    city: dict[str, Any],
    api_config: dict[str, Any],
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Fetch one archive chunk for one city."""
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": ",".join(api_config["hourly_variables"]),
        "timezone": api_config["timezone"],
    }
    max_retries = api_config["max_retries"]

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                api_config["archive_url"],
                params=params,
                timeout=api_config["timeout_seconds"],
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            if not _is_retryable(error) or attempt == max_retries:
                logger.error(
                    "Failed archive extraction for %s (%s to %s): %s",
                    city["name"],
                    start_date.isoformat(),
                    end_date.isoformat(),
                    error,
                )
                raise

            delay = 2**attempt
            logger.warning(
                "Retrying archive extraction for %s after attempt %d/%d: "
                "waiting %d second(s)",
                city["name"],
                attempt + 1,
                max_retries + 1,
                delay,
            )
            time.sleep(delay)

    raise RuntimeError("Archive request retry loop ended unexpectedly.")


def extract_archive(
    config: dict[str, Any],
    start_date: date,
    end_date: date,
    sleep_seconds: float = 1.0,
) -> list[tuple[str, dict[str, Any]]]:
    """Fetch and save historical archive chunks for every configured city."""
    api_config = config["api"]
    raw_directory = Path(config["paths"]["raw_dir"])
    now = datetime.now(timezone.utc)
    run_folder = raw_directory / "archive" / now.strftime("%Y-%m-%d")
    run_folder.mkdir(parents=True, exist_ok=True)

    payloads = []
    chunks = iter_archive_chunks(start_date, end_date)
    city_count = len(config["cities"])
    for city_index, city in enumerate(config["cities"]):
        for chunk_index, (chunk_start, chunk_end) in enumerate(chunks):
            logger.info(
                "Fetching archive chunk for %s: %s to %s",
                city["name"],
                chunk_start.isoformat(),
                chunk_end.isoformat(),
            )
            payload = _fetch_archive_payload(
                city,
                api_config,
                chunk_start,
                chunk_end,
            )
            clean_name = city["name"].lower().replace(" ", "_")
            file_name = (
                f"{clean_name}_{chunk_start.isoformat()}_{chunk_end.isoformat()}.json"
            )
            file_path = run_folder / file_name
            with file_path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
            payloads.append((city["name"], payload))
            logger.info("Saved archive payload to %s", file_path)

            is_last_request = (
                city_index == city_count - 1
                and chunk_index == len(chunks) - 1
            )
            if not is_last_request:
                time.sleep(sleep_seconds)

    return payloads


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
