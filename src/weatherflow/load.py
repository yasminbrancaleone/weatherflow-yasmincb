## Database schema and dimension/fact loading.

from contextlib import closing
from datetime import date, datetime, timedelta
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import sqlite3


logger = logging.getLogger(__name__)
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def _parse_date(value: date | datetime | str) -> date:
    """Parse a configured date or date-like value."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _iter_dates(start: date, end: date):
    """Yield dates in the inclusive range."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def load_dimensions(
    config: dict[str, Any], db_path: Path | str
) -> tuple[int, int]:
    """Create the schema and upsert configured dimension rows."""
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

        with connection:
            cursor = connection.cursor()
            cursor.executemany(
                """
                INSERT INTO dim_city (city_name, country, latitude, longitude)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(city_name) DO UPDATE SET
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

            dim_date = config["dim_date"]
            date_rows = []
            for current_date in _iter_dates(
                _parse_date(dim_date["start"]),
                _parse_date(dim_date["end"]),
            ):
                date_rows.append(
                    (
                        int(current_date.strftime("%Y%m%d")),
                        current_date.isoformat(),
                        current_date.strftime("%A"),
                        int(current_date.weekday() >= 5),
                        current_date.month,
                        current_date.year,
                    )
                )
            cursor.executemany(
                """
                INSERT INTO dim_date (
                    date_id, full_date, day_of_week, is_weekend, month, year
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date_id) DO UPDATE SET
                    full_date = excluded.full_date,
                    day_of_week = excluded.day_of_week,
                    is_weekend = excluded.is_weekend,
                    month = excluded.month,
                    year = excluded.year
                """,
                date_rows,
            )

            city_count = cursor.execute(
                "SELECT COUNT(*) FROM dim_city"
            ).fetchone()[0]
            date_count = cursor.execute(
                "SELECT COUNT(*) FROM dim_date"
            ).fetchone()[0]

    logger.info(
        "Loaded %d cities and %d dates into dimension tables.",
        city_count,
        date_count,
    )
    return city_count, date_count


def _canonical_utc(value: datetime | pd.Timestamp | str) -> str:
    """Serialize a timestamp as canonical UTC text."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat(timespec="seconds")


def canonicalize_observed_at(value: datetime | pd.Timestamp | str) -> str:
    """Serialize observation timestamps consistently for SQLite keys."""
    return _canonical_utc(value)


def _build_fact_rows(
    dataframe: pd.DataFrame,
    connection: sqlite3.Connection,
    source: str,
) -> list[tuple[Any, ...]]:
    """Resolve dimension keys and build fact table rows."""
    city_ids = dict(
        connection.execute(
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

        date_id = int(observed_local.strftime("%Y%m%d"))
        date_exists = connection.execute(
            "SELECT 1 FROM dim_date WHERE date_id = ?", (date_id,)
        ).fetchone()
        if date_exists is None:
            raise ValueError(
                f"Observation date {observed_local.date()} is missing from dim_date"
            )

        fact_rows.append(
            (
                city_id,
                date_id,
                _canonical_utc(row.observed_at_utc),
                int(observed_local.hour),
                getattr(row, "temperature_c", None),
                getattr(row, "feels_like_c", None),
                getattr(row, "humidity_pct", None),
                getattr(row, "precipitation_mm", None),
                getattr(row, "wind_speed_kmh", None),
                getattr(row, "wind_speed_ms", None),
                getattr(row, "weather_code", None),
                getattr(row, "description", None),
                getattr(row, "category", None),
                getattr(row, "temperature_f", None),
                getattr(row, "beaufort_scale", None),
                int(bool(getattr(row, "is_daylight", False))),
                row.outdoor_work_risk,
                source,
                _canonical_utc(row.ingested_at_utc),
            )
        )

    return fact_rows


def load(
    dataframe: pd.DataFrame,
    db_path: Path | str,
    config: dict[str, Any] | None = None,
    source: str = "open-meteo",
) -> int:
    """Load fact rows atomically with composite-key upserts."""
    if dataframe.empty:
        logger.warning("No data available for loading.")
        return 0

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

        if config is not None:
            load_dimensions(config, db_path)
        else:
            with connection:
                cursor = connection.cursor()
                cursor.executemany(
                    """
                    INSERT INTO dim_city (city_name, country, latitude, longitude)
                    VALUES (?, 'Unknown', 0.0, 0.0)
                    ON CONFLICT(city_name) DO NOTHING
                    """,
                    [(city,) for city in sorted(dataframe["city"].unique())],
                )
                for observed_local in pd.to_datetime(
                    dataframe["observed_at_local"], utc=True
                ).dt.tz_convert("Europe/London"):
                    current_date = observed_local.date()
                    cursor.execute(
                        """
                        INSERT INTO dim_date (
                            date_id, full_date, day_of_week, is_weekend, month, year
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(date_id) DO NOTHING
                        """,
                        (
                            int(current_date.strftime("%Y%m%d")),
                            current_date.isoformat(),
                            current_date.strftime("%A"),
                            int(current_date.weekday() >= 5),
                            current_date.month,
                            current_date.year,
                        ),
                    )

        fact_rows = _build_fact_rows(dataframe, connection, source)
        upsert_sql = """
            INSERT INTO fact_weather_hourly (
                city_id, date_id, observed_at_utc, hour_local,
                temperature_c, feels_like_c, humidity_pct, precipitation_mm,
                wind_speed_kmh, wind_speed_ms, weather_code, description, category,
                temperature_f, beaufort_scale, is_daylight, outdoor_work_risk,
                source, ingested_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        """

        try:
            with connection:
                connection.executemany(upsert_sql, fact_rows)
        except sqlite3.Error:
            logger.exception("Atomic fact load failed; transaction was rolled back.")
            raise

    logger.info(
        "Loaded %d fact rows from source %s.", len(fact_rows), source
    )
    return len(fact_rows)
