from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any
from urllib.parse import quote, quote_plus

import requests


logger = logging.getLogger(__name__)

_SECRET_LOGGERS = (
    "requests",
    "requests.adapters",
    "requests.api",
    "requests.models",
    "requests.sessions",
    "requests.packages.urllib3.connectionpool",
    "urllib3",
    "urllib3.connection",
    "urllib3.connectionpool",
    "urllib3.poolmanager",
    "urllib3.util.retry",
)


class _SecretRedactionFilter(logging.Filter):
    """Redact a secret from HTTP-library log records."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self.secret_variants = {
            secret,
            quote(secret, safe=""),
            quote_plus(secret),
        }

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secret_variants:
            message = message.replace(secret, "[REDACTED]")
        if message != record.getMessage():
            record.msg = message
            record.args = ()
        return True


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


def _get_with_retries(
    url: str,
    params: dict[str, Any],
    api_config: dict[str, Any],
    context: str,
    secret: str | None = None,
) -> dict[str, Any]:
    """GET a weather API payload with retry and exponential backoff."""
    max_retries = api_config["max_retries"]
    secret_loggers = []
    redaction_filter = None
    if secret:
        redaction_filter = _SecretRedactionFilter(secret)
        secret_loggers = [
            logging.getLogger(name) for name in _SECRET_LOGGERS
        ]
        for secret_logger in secret_loggers:
            secret_logger.addFilter(redaction_filter)

    try:
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=api_config["timeout_seconds"],
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as error:
                retryable = _is_retryable(error)
                if not retryable or attempt == max_retries:
                    if secret:
                        status_code = (
                            error.response.status_code
                            if error.response is not None
                            else None
                        )
                        reason = (
                            f"HTTP status {status_code}"
                            if status_code is not None
                            else type(error).__name__
                        )
                        safe_message = f"Failed {context} ({reason})."
                        logger.error("%s", safe_message)
                        raise requests.RequestException(safe_message) from None
                    logger.error("Failed %s: %s", context, error)
                    raise

                delay = 2**attempt
                if secret:
                    status_code = (
                        error.response.status_code
                        if error.response is not None
                        else None
                    )
                    reason = (
                        f"HTTP status {status_code}"
                        if status_code is not None
                        else type(error).__name__
                    )
                    logger.warning(
                        "Retrying %s after attempt %d/%d due to %s; "
                        "waiting %d second(s)",
                        context,
                        attempt + 1,
                        max_retries + 1,
                        reason,
                        delay,
                    )
                else:
                    logger.warning(
                        "Retrying %s after attempt %d/%d: %s; "
                        "waiting %d second(s)",
                        context,
                        attempt + 1,
                        max_retries + 1,
                        error,
                        delay,
                    )
                time.sleep(delay)

        raise RuntimeError("Request retry loop ended unexpectedly.")
    finally:
        for secret_logger in secret_loggers:
            secret_logger.removeFilter(redaction_filter)


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
    return _get_with_retries(
        api_config["forecast_url"],
        params,
        api_config,
        f"forecast extraction for {city['name']}",
    )


def build_incremental_window(
    db_path: Path | str,
    city_name: str,
    source: str,
    past_days: int,
    forecast_days: int,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build an incremental API window with a two-hour overlap."""
    database_reference = str(db_path)
    if database_reference.startswith(("postgresql://", "postgres://")):
        from .postgres import get_high_water_mark
    else:
        from .load import get_high_water_mark

    current_time = now_utc or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    end_time = current_time + timedelta(days=forecast_days)
    high_water_mark = get_high_water_mark(
        db_path,
        city_name,
        source,
        current_time,
    )
    if high_water_mark is not None:
        start_time = high_water_mark - timedelta(hours=2)
        window_source = "high-water-mark"
    else:
        start_time = current_time - timedelta(days=past_days)
        window_source = "past-days-fallback"

    if start_time > end_time:
        raise ValueError("Incremental start time must be before forecast end time.")

    logger.info(
        "Incremental request window for %s: %s to %s (%s)",
        city_name,
        start_time.isoformat(),
        end_time.isoformat(),
        window_source,
    )
    return {
        "start_time": start_time,
        "end_time": end_time,
        "source": window_source,
    }


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
    return _get_with_retries(
        api_config["archive_url"],
        params,
        api_config,
        f"archive extraction for {city['name']} "
        f"({start_date.isoformat()} to {end_date.isoformat()})",
    )


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


def extract_incremental(
    config: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Fetch recent and forecast hours using one city-specific watermark."""
    from .config import get_database_url

    api_config = config["api"]
    database_reference = (
        get_database_url() or config["paths"]["database"]
    )
    raw_directory = Path(config["paths"]["raw_dir"])
    now = datetime.now(timezone.utc)
    run_folder = raw_directory / now.strftime("%Y-%m-%d")
    run_folder.mkdir(parents=True, exist_ok=True)

    payloads = []
    for city in config["cities"]:
        window = build_incremental_window(
            database_reference,
            city["name"],
            "open_meteo_forecast",
            past_days=api_config["past_days"],
            forecast_days=api_config["forecast_days"],
            now_utc=now,
        )
        params = {
            "latitude": city["latitude"],
            "longitude": city["longitude"],
            "hourly": ",".join(api_config["hourly_variables"]),
            "start_date": window["start_time"].strftime("%Y-%m-%d"),
            "end_date": window["end_time"].strftime("%Y-%m-%d"),
            "timezone": api_config["timezone"],
        }
        logger.info(
            "Incremental API window for %s: %s to %s",
            city["name"],
            params["start_date"],
            params["end_date"],
        )
        payload = _fetch_payload_from_forecast_window(
            city,
            api_config,
            params,
        )

        clean_name = city["name"].lower().replace(" ", "_")
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        file_path = run_folder / f"{clean_name}_{timestamp}.json"
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
        payloads.append((city["name"], payload))
        logger.info("Saved incremental payload to %s", file_path)

    return payloads


def extract_weatherapi(
    config: dict[str, Any],
    api_key: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Fetch and save WeatherAPI forecast payloads for configured cities."""
    from .config import load_weatherapi_key

    resolved_api_key = api_key or load_weatherapi_key()
    api_config = config["api"]
    raw_directory = Path(config["paths"]["raw_dir"])
    now = datetime.now(timezone.utc)
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    folder_path = raw_directory / date_folder
    folder_path.mkdir(parents=True, exist_ok=True)

    raw_payloads: list[tuple[str, dict[str, Any]]] = []
    for city in config["cities"]:
        payload = _get_with_retries(
            api_config["weatherapi_forecast_url"],
            {
                "key": resolved_api_key,
                "q": f"{city['latitude']},{city['longitude']}",
                "days": api_config["forecast_days"],
            },
            api_config,
            f"WeatherAPI forecast extraction for {city['name']}",
            secret=resolved_api_key,
        )

        clean_name = city["name"].lower().replace(" ", "_")
        file_path = folder_path / f"{clean_name}_weatherapi_{timestamp}.json"
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

        raw_payloads.append((city["name"], payload))
        logger.info("Saved WeatherAPI raw payload for %s", city["name"])

    return raw_payloads


def _fetch_payload_from_forecast_window(
    city: dict[str, Any],
    api_config: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Fetch an incremental forecast window with the configured retries."""
    return _get_with_retries(
        api_config["forecast_url"],
        params,
        api_config,
        f"incremental extraction for {city['name']}",
    )


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
