"""PostgreSQL warehouse loading."""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from .load import _iter_dates, _optional_int, _parse_date


logger = logging.getLogger(__name__)
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "sql" / "schema_postgres.sql"

_UPSERT_FACT_SQL = """
    INSERT INTO fact_weather_hourly (
        city_id, date_id, observed_at_utc, hour_local,
        temperature_c, feels_like_c, humidity_pct, precipitation_mm,
        wind_speed_kmh, wind_speed_ms, weather_code, description, category,
        temperature_f, beaufort_scale, is_daylight, outdoor_work_risk,
        source, ingested_at_utc
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (city_id, observed_at_utc, source) DO UPDATE SET
        date_id = excluded.date_id,
        hour_local = excluded.hour_local,
        temperature_c = excluded.temperature_c,
        feels_like_c = excluded.feels_like_c,
        humidity_pct = excluded.humidity_pct,
        precipitation_mm = excluded.precipitation_mm,
        wind_speed_kmh = excluded.wind_speed_kmh,
        wind_speed_ms = excluded.wind_speed_ms,
        weather_code = excluded.weather_code,
        description = excluded.description,
        category = excluded.category,
        temperature_f = excluded.temperature_f,
        beaufort_scale = excluded.beaufort_scale,
        is_daylight = excluded.is_daylight,
        outdoor_work_risk = excluded.outdoor_work_risk,
        ingested_at_utc = excluded.ingested_at_utc
    RETURNING (xmax = 0) AS inserted
"""


def _execute_schema(cursor: psycopg.Cursor[Any]) -> None:
    """Create missing warehouse tables inside the caller's transaction."""
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    for statement in schema.split(";"):
        if statement.strip():
            cursor.execute(statement)


def ensure_schema(database_url: str) -> None:
    """Create missing warehouse tables without loading fact data."""
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            _execute_schema(cursor)


def _upsert_dimensions(
    cursor: psycopg.Cursor[Any],
    config: dict[str, Any],
) -> None:
    cursor.executemany(
        """
        INSERT INTO dim_city (city_name, country, latitude, longitude)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (city_name) DO UPDATE SET
            country = excluded.country,
            latitude = excluded.latitude,
            longitude = excluded.longitude
        """,
        [
            (
                city["name"],
                city["country"],
                city["latitude"],
                city["longitude"],
            )
            for city in config["cities"]
        ],
    )

    date_config = config["dim_date"]
    start_date = _parse_date(date_config["start"])
    end_date = _parse_date(date_config["end"])
    cursor.executemany(
        """
        INSERT INTO dim_date (
            date_id, full_date, day_of_week, is_weekend, month, year
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (date_id) DO UPDATE SET
            full_date = excluded.full_date,
            day_of_week = excluded.day_of_week,
            is_weekend = excluded.is_weekend,
            month = excluded.month,
            year = excluded.year
        """,
        [
            (
                int(current_date.strftime("%Y%m%d")),
                current_date,
                current_date.strftime("%A"),
                current_date.weekday() >= 5,
                current_date.month,
                current_date.year,
            )
            for current_date in _iter_dates(start_date, end_date)
        ],
    )


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return bool(value)


def _optional_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)


def _aware_utc(value: datetime | pd.Timestamp | str) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()


def _build_fact_rows(
    dataframe: pd.DataFrame,
    cursor: psycopg.Cursor[Any],
    source: str,
) -> list[tuple[Any, ...]]:
    city_ids = dict(
        cursor.execute(
            "SELECT city_name, city_id FROM dim_city"
        ).fetchall()
    )
    fact_rows = []

    for row in dataframe.itertuples(index=False):
        city_id = city_ids.get(row.city)
        if city_id is None:
            raise ValueError(f"Unknown city in fact data: {row.city}")

        observed_local = pd.Timestamp(row.observed_at_local)
        if observed_local.tzinfo is None:
            observed_local = observed_local.tz_localize(
                "Europe/London",
                ambiguous="raise",
                nonexistent="raise",
            )
        else:
            observed_local = observed_local.tz_convert("Europe/London")

        fact_rows.append(
            (
                city_id,
                int(observed_local.strftime("%Y%m%d")),
                _aware_utc(row.observed_at_utc),
                int(observed_local.hour),
                _optional_float(getattr(row, "temperature_c", None)),
                _optional_float(getattr(row, "feels_like_c", None)),
                _optional_int(getattr(row, "humidity_pct", None)),
                _optional_float(getattr(row, "precipitation_mm", None)),
                _optional_float(getattr(row, "wind_speed_kmh", None)),
                _optional_float(getattr(row, "wind_speed_ms", None)),
                _optional_int(getattr(row, "weather_code", None)),
                _optional_text(getattr(row, "description", None)),
                _optional_text(getattr(row, "category", None)),
                _optional_float(getattr(row, "temperature_f", None)),
                _optional_int(getattr(row, "beaufort_scale", None)),
                _optional_bool(getattr(row, "is_daylight", None)),
                row.outdoor_work_risk,
                source,
                _aware_utc(row.ingested_at_utc),
            )
        )

    return fact_rows


def load_with_counts(
    dataframe: pd.DataFrame,
    database_url: str,
    config: dict[str, Any],
    source: str,
) -> tuple[int, int]:
    """Atomically upsert dimensions and facts; return new and updated counts."""
    if dataframe.empty:
        logger.warning("No data available for PostgreSQL loading.")
        return 0, 0

    new_rows = 0
    updated_rows = 0
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                _execute_schema(cursor)
                _upsert_dimensions(cursor, config)
                fact_rows = _build_fact_rows(dataframe, cursor, source)
                for fact_row in fact_rows:
                    inserted = cursor.execute(
                        _UPSERT_FACT_SQL,
                        fact_row,
                    ).fetchone()[0]
                    if inserted:
                        new_rows += 1
                    else:
                        updated_rows += 1

    logger.info(
        "PostgreSQL load from source %s: %d new rows, %d updated rows.",
        source,
        new_rows,
        updated_rows,
    )
    return new_rows, updated_rows


def get_high_water_mark(
    database_url: str,
    city_name: str,
    source: str,
    now_utc: datetime | None = None,
) -> datetime | None:
    """Read the latest loaded past-hour for a city and source."""
    current_time = now_utc or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT MAX(fact.observed_at_utc)
            FROM fact_weather_hourly AS fact
            JOIN dim_city AS city ON city.city_id = fact.city_id
            WHERE city.city_name = %s
              AND fact.source = %s
              AND fact.observed_at_utc <= %s
            """,
            (city_name, source, current_time),
        ).fetchone()

    if row is None or row[0] is None:
        return None
    return pd.Timestamp(row[0]).tz_convert("UTC").to_pydatetime()
