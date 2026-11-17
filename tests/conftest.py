"""Shared pytest fixtures for WeatherFlow tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def london_payload():
    """Load the trimmed London Open-Meteo fixture using UTF-8."""
    fixture_path = Path(__file__).parent / "fixtures" / "open_meteo_london.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))
