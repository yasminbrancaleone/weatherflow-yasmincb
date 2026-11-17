from contextlib import closing
from datetime import datetime
import logging
from pathlib import Path

import pandas as pd
import sqlite3


logger = logging.getLogger(__name__)


def canonicalize_observed_at(value: datetime | pd.Timestamp | str) -> str:
    """Serialize observation timestamps consistently for SQLite keys."""
    return pd.Timestamp(value).strftime("%Y-%m-%dT%H:%M:%S")


def load(df: pd.DataFrame, db_path: Path | str) -> int:
    """Create the weather table and insert rows idempotently."""
    if df.empty:
        logger.warning("No data available for loading.")
        return 0

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS weather_hourly (
        city            TEXT    NOT NULL,
        observed_at     TEXT    NOT NULL,
        temperature_c   REAL,
        feels_like_c    REAL,
        humidity_pct    INTEGER,
        precipitation_mm REAL,
        wind_speed_kmh  REAL,
        weather_code    INTEGER,
        ingested_at_utc TEXT    NOT NULL,
        PRIMARY KEY (city, observed_at)
    );
    """
    insert_sql = """
    INSERT OR REPLACE INTO weather_hourly (
        city, observed_at, temperature_c, feels_like_c,
        humidity_pct, precipitation_mm, wind_speed_kmh,
        weather_code, ingested_at_utc
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    dataframe = df.copy()
    dataframe["observed_at"] = dataframe["observed_at"].map(
        canonicalize_observed_at
    )
    data_to_insert = [tuple(row) for row in dataframe.itertuples(index=False)]

    with closing(sqlite3.connect(db_path)) as connection, connection:
        cursor = connection.cursor()
        cursor.execute(create_table_sql)
        existing_rows = cursor.execute(
            """
            SELECT city, observed_at, temperature_c, feels_like_c, humidity_pct,
                   precipitation_mm, wind_speed_kmh, weather_code, ingested_at_utc
            FROM weather_hourly
            ORDER BY ingested_at_utc, observed_at
            """
        ).fetchall()

        latest_by_key = {}
        for row in existing_rows:
            normalized_row = (
                row[0],
                canonicalize_observed_at(row[1]),
                *row[2:],
            )
            latest_by_key[(normalized_row[0], normalized_row[1])] = normalized_row

        if existing_rows:
            cursor.execute("DELETE FROM weather_hourly")
            cursor.executemany(insert_sql, latest_by_key.values())

        cursor.executemany(insert_sql, data_to_insert)

    logger.info("Loaded %d weather observations into %s.", len(data_to_insert), db_path)
    return len(data_to_insert)
