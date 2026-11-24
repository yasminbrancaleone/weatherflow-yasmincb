"""Tests for backfill chunks and incremental high-water marks."""

import sqlite3
from datetime import date, datetime, timezone

import pandas as pd

from weatherflow.config import load_config
from weatherflow.extract import build_incremental_window, iter_archive_chunks
from weatherflow.load import get_high_water_mark, load_with_counts


def test_archive_range_is_split_into_seven_day_chunks():
    """A 30-day range is split into seven-day chunks with a short final chunk."""
    chunks = iter_archive_chunks(
        date(2026, 10, 14),
        date(2026, 11, 12),
    )

    assert chunks == [
        (date(2026, 10, 14), date(2026, 10, 20)),
        (date(2026, 10, 21), date(2026, 10, 27)),
        (date(2026, 10, 28), date(2026, 11, 3)),
        (date(2026, 11, 4), date(2026, 11, 10)),
        (date(2026, 11, 11), date(2026, 11, 12)),
    ]


def test_incremental_window_without_data_uses_past_days(tmp_path):
    """A first run falls back to past_days when no watermark exists."""
    database = tmp_path / "empty.db"
    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    window = build_incremental_window(
        database,
        "London",
        "open_meteo_forecast",
        past_days=1,
        forecast_days=7,
        now_utc=now,
    )

    assert window["source"] == "past-days-fallback"
    assert window["start_time"] == datetime(
        2026, 11, 16, 12, 0, tzinfo=timezone.utc
    )
    assert window["end_time"] == datetime(
        2026, 11, 24, 12, 0, tzinfo=timezone.utc
    )


def test_incremental_window_uses_postgres_high_water_mark(monkeypatch):
    """A PostgreSQL URL routes watermark reads to the PostgreSQL loader."""
    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    high_water_mark = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    calls = []

    def fake_get_high_water_mark(database_url, city_name, source, current_time):
        calls.append((database_url, city_name, source, current_time))
        return high_water_mark

    monkeypatch.setattr(
        "weatherflow.postgres.get_high_water_mark",
        fake_get_high_water_mark,
    )

    window = build_incremental_window(
        "postgresql://weatherflow:example@localhost:5433/weatherflow",
        "London",
        "open_meteo_forecast",
        past_days=1,
        forecast_days=1,
        now_utc=now,
    )

    assert calls == [
        (
            "postgresql://weatherflow:example@localhost:5433/weatherflow",
            "London",
            "open_meteo_forecast",
            now,
        )
    ]
    assert window["source"] == "high-water-mark"
    assert window["start_time"] == datetime(
        2026, 11, 17, 8, 0, tzinfo=timezone.utc
    )


def test_high_water_mark_ignores_future_forecast_rows(tmp_path):
    """The watermark uses only past and current rows, not forecast rows."""
    database = tmp_path / "weather.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            open("sql/schema.sql", encoding="utf-8").read()
        )
        connection.execute(
            """
            INSERT INTO dim_city (city_name, country, latitude, longitude)
            VALUES (?, ?, ?, ?)
            """,
            ("London", "United Kingdom", 51.5085, -0.1257),
        )
        connection.execute(
            """
            INSERT INTO dim_date
                (date_id, full_date, day_of_week, is_weekend, month, year)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (20261117, "2026-11-17", "Tuesday", 0, 11, 2026),
        )
        connection.execute(
            """
            INSERT INTO dim_date
                (date_id, full_date, day_of_week, is_weekend, month, year)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (20261118, "2026-11-18", "Wednesday", 0, 11, 2026),
        )
        connection.execute(
            """
            INSERT INTO fact_weather_hourly
                (city_id, date_id, observed_at_utc, hour_local,
                 outdoor_work_risk, source, ingested_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                20261117,
                "2026-11-17T10:00:00+00:00",
                10,
                "low",
                "open_meteo_forecast",
                "2026-11-17T10:05:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO fact_weather_hourly
                (city_id, date_id, observed_at_utc, hour_local,
                 outdoor_work_risk, source, ingested_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                20261118,
                "2026-11-18T10:00:00+00:00",
                10,
                "low",
                "open_meteo_forecast",
                "2026-11-17T12:05:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    mark = get_high_water_mark(
        database,
        "London",
        "open_meteo_forecast",
        now,
    )

    assert mark == pd.Timestamp("2026-11-17T10:00:00Z")

    window = build_incremental_window(
        database,
        "London",
        "open_meteo_forecast",
        past_days=1,
        forecast_days=7,
        now_utc=now,
    )
    assert window["source"] == "high-water-mark"
    assert window["start_time"] == datetime(
        2026, 11, 17, 8, 0, tzinfo=timezone.utc
    )


def test_second_load_updates_fact_without_increasing_row_count(tmp_path):
    """A repeated load reports one update and keeps one fact row."""
    config = load_config()
    database = tmp_path / "weather.db"
    dataframe = pd.DataFrame(
        [
            {
                "city": "London",
                "observed_at_utc": pd.Timestamp("2026-11-17T12:00:00Z"),
                "observed_at_local": pd.Timestamp(
                    "2026-11-17T12:00:00Z"
                ).tz_convert("Europe/London"),
                "temperature_c": 10.0,
                "feels_like_c": 10.0,
                "humidity_pct": 70,
                "precipitation_mm": 0.0,
                "wind_speed_kmh": 10.0,
                "wind_speed_ms": 2.78,
                "weather_code": 63,
                "description": "Moderate rain",
                "category": "rain",
                "temperature_f": 50.0,
                "beaufort_scale": 2,
                "is_daylight": True,
                "outdoor_work_risk": "low",
                "ingested_at_utc": pd.Timestamp("2026-11-17T12:05:00Z"),
            }
        ]
    )

    first = load_with_counts(
        dataframe,
        database,
        config,
        "open_meteo_forecast",
    )
    second = load_with_counts(
        dataframe,
        database,
        config,
        "open_meteo_forecast",
    )

    assert first == (1, 0)
    assert second == (0, 1)

    connection = sqlite3.connect(database)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM fact_weather_hourly"
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1
