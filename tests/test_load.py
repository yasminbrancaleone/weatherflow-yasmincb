"""Integration tests for the star schema fact loader."""

import sqlite3

from weatherflow.config import load_config
from weatherflow.load import load
from weatherflow.reference import load_wmo_codes
from weatherflow.transform import transform


def test_loading_fixture_twice_keeps_fact_row_count(london_payload, tmp_path):
    """The composite fact key makes repeated fixture loads idempotent."""
    database = tmp_path / "weather.db"
    config = load_config()

    transformed = transform(
        [("London", london_payload)],
        load_wmo_codes(),
    )

    first_count = load(
        transformed,
        database,
        config=config,
    )
    second_count = load(
        transformed,
        database,
        config=config,
    )

    assert first_count == 6
    assert second_count == 6

    connection = sqlite3.connect(database)
    try:
        fact_count = connection.execute(
            "SELECT COUNT(*) FROM fact_weather_hourly"
        ).fetchone()[0]
        city_count = connection.execute(
            "SELECT COUNT(*) FROM dim_city"
        ).fetchone()[0]
    finally:
        connection.close()

    assert fact_count == 6
    assert city_count == 5
