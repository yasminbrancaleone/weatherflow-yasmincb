from datetime import datetime, timezone
import json
from pathlib import Path
import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"

# 5 cities in the United Kingdom with their geographical coordinates.
CITIES = [
    {"name": "London", "latitude": 51.5085, "longitude": -0.1257},
    {"name": "Manchester", "latitude": 53.4808, "longitude": -2.2426},
    {"name": "Birmingham", "latitude": 52.4862, "longitude": -1.8904},
    {"name": "Edinburgh", "latitude": 55.9533, "longitude": -3.1883},
    {"name": "Cardiff", "latitude": 51.4816, "longitude": -3.1791},
]


def fetch_city(city: dict) -> dict:
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,wind_speed_10m,weather_code"
        ),
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "Europe/London",
    }
    response = requests.get(BASE_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()

def save_raw(city_name: str, payload: dict) -> Path:
    now = datetime.now(timezone.utc)
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    # Create the directory data/raw/YYYY-MM-DD/ if it doesn't exist.
    folder_path = Path("data") / "raw" / date_folder
    folder_path.mkdir(parents=True, exist_ok=True)

    clean_city_name = city_name.lower().replace(" ", "_")
    file_name = f"{clean_city_name}_{timestamp}.json"
    file_path = folder_path / file_name

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return file_path

def main():
    print("Starting raw weather data extraction...")
    for city in CITIES:
        try:
            payload = fetch_city(city)
            file_path = save_raw(city["name"], payload)
            hourly_records = len(payload.get("hourly", {}).get("time", []))
            print(
                f"[SUCCESS] {city['name']}: {hourly_records} hourly records"
                f" saved to {file_path}"
            )
        except requests.RequestException as e:
            print(f"[ERROR] Failed to fetch data for {city['name']}: {e}")


if __name__ == "__main__":
    main()