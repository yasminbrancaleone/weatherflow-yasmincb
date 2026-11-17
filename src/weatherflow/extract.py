from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import requests


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
        params = {
            "latitude": city["latitude"],
            "longitude": city["longitude"],
            "hourly": ",".join(api_config["hourly_variables"]),
            "past_days": api_config["past_days"],
            "forecast_days": api_config["forecast_days"],
            "timezone": api_config["timezone"],
        }
        response = requests.get(
            api_config["forecast_url"],
            params=params,
            timeout=api_config["timeout_seconds"],
        )
        response.raise_for_status()
        payload = response.json()

        clean_name = city["name"].lower().replace(" ", "_")
        file_path = folder_path / f"{clean_name}_{timestamp}.json"
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

        raw_payloads.append((city["name"], payload))

    return raw_payloads
