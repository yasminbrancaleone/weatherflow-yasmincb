from contextlib import closing
from datetime import datetime
import logging
from pathlib import Path

import pandas as pd
import sqlite3


logger = logging.getLogger(__name__)


def canonicalize_observed_at(value: datetime | pd.Timestamp | str) -> str:
    """Serialize observation timestamps consistently for SQLite keys."""
    return pd.Timestamp(value).isoformat(timespec="seconds")


def _create_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_hourly (
            city             TEXT    NOT NULL,
            observed_at_utc  TEXT    NOT NULL,
            observed_at_local TEXT   NOT NULL,
            temperature_c    REAL,
            feels_like_c     REAL,
            humidity_pct     INTEGER,
            precipitation_mm REAL,
            wind_speed_kmh   REAL,
            weather_code     INTEGER,
            description      TEXT,
            category         TEXT,
            temperature_f    REAL,
            wind_speed_ms    REAL,
            beaufort_scale   INTEGER,
            is_daylight      INTEGER,
            outdoor_work_risk TEXT,
            ingested_at_utc  TEXT   NOT NULL,
            PRIMARY KEY (city, observed_at_utc)
        );
        """
    )


def _migrate_legacy_rows(
    cursor: sqlite3.Cursor, insert_sql: str
) -> None:
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(weather_hourly)")
    }
    if "observed_at_utc" in columns or not columns:
        return

    legacy_rows = cursor.execute(
        """
        SELECT city, observed_at, temperature_c, feels_like_c, humidity_pct,
               precipitation_mm, wind_speed_kmh, weather_code, ingested_at_utc
        FROM weather_hourly
        """
    ).fetchall()
    cursor.execute("ALTER TABLE weather_hourly RENAME TO weather_hourly_legacy")
    _create_table(cursor)

    migrated_rows = []
    for row in legacy_rows:
        local_timestamp = pd.Timestamp(row[1])
        if local_timestamp.tzinfo is None:
            local_timestamp = local_timestamp.tz_localize(
                "Europe/London", ambiguous="raise", nonexistent="raise"
            )
        utc_timestamp = local_timestamp.tz_convert("UTC")
        migrated_rows.append(
            (
                row[0],
                canonicalize_observed_at(utc_timestamp),
                canonicalize_observed_at(local_timestamp),
                *row[2:8],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                row[8],
            )
        )

    cursor.executemany(insert_sql, migrated_rows)
    cursor.execute("DROP TABLE weather_hourly_legacy")


def _ensure_reference_columns(cursor: sqlite3.Cursor) -> None:
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(weather_hourly)")
    }
    if "description" not in columns:
        cursor.execute("ALTER TABLE weather_hourly ADD COLUMN description TEXT")
    if "category" not in columns:
        cursor.execute("ALTER TABLE weather_hourly ADD COLUMN category TEXT")
    if "temperature_f" not in columns:
        cursor.execute("ALTER TABLE weather_hourly ADD COLUMN temperature_f REAL")
    if "wind_speed_ms" not in columns:
        cursor.execute("ALTER TABLE weather_hourly ADD COLUMN wind_speed_ms REAL")
    if "beaufort_scale" not in columns:
        cursor.execute("ALTER TABLE weather_hourly ADD COLUMN beaufort_scale INTEGER")
    if "is_daylight" not in columns:
        cursor.execute("ALTER TABLE weather_hourly ADD COLUMN is_daylight INTEGER")
    if "outdoor_work_risk" not in columns:
        cursor.execute(
            "ALTER TABLE weather_hourly ADD COLUMN outdoor_work_risk TEXT"
        )


def load(df: pd.DataFrame, db_path: Path | str) -> int:
    """Create the weather table and insert rows idempotently."""
    if df.empty:
        logger.warning("No data available for loading.")
        return 0

    insert_sql = """
    INSERT OR REPLACE INTO weather_hourly (
        city, observed_at_utc, observed_at_local, temperature_c, feels_like_c,
        humidity_pct, precipitation_mm, wind_speed_kmh,
        weather_code, description, category, temperature_f, wind_speed_ms,
        beaufort_scale, is_daylight, outdoor_work_risk, ingested_at_utc
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    dataframe = df.copy()
    dataframe["observed_at_utc"] = dataframe["observed_at_utc"].map(
        canonicalize_observed_at
    )
    dataframe["observed_at_local"] = dataframe["observed_at_local"].map(
        canonicalize_observed_at
    )
    data_to_insert = [tuple(row) for row in dataframe.itertuples(index=False)]

    with closing(sqlite3.connect(db_path)) as connection, connection:
        cursor = connection.cursor()
        _create_table(cursor)
        _migrate_legacy_rows(cursor, insert_sql)
        _ensure_reference_columns(cursor)
        existing_rows = cursor.execute(
            """
            SELECT city, observed_at_utc, observed_at_local, temperature_c,
                   feels_like_c, humidity_pct, precipitation_mm, wind_speed_kmh,
            weather_code, description, category, temperature_f,
            wind_speed_ms, beaufort_scale, is_daylight, outdoor_work_risk,
            ingested_at_utc
            FROM weather_hourly
            ORDER BY ingested_at_utc, observed_at_utc
            """
        ).fetchall()

        latest_by_key = {}
        for row in existing_rows:
            normalized_row = (
                row[0],
                canonicalize_observed_at(row[1]),
                canonicalize_observed_at(row[2]),
                *row[3:],
            )
            latest_by_key[(normalized_row[0], normalized_row[1])] = (
                normalized_row
            )

        if existing_rows:
            cursor.execute("DELETE FROM weather_hourly")
            cursor.executemany(insert_sql, latest_by_key.values())

        cursor.executemany(insert_sql, data_to_insert)

    logger.info("Loaded %d weather observations into %s.", len(data_to_insert), db_path)
    return len(data_to_insert)
