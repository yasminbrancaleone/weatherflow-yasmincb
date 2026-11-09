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