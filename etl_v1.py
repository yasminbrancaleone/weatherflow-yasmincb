from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import pandas as pd
import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"
CITIES = [
    {"name": "London", "latitude": 51.5085, "longitude": -0.1257},
    {"name": "Manchester", "latitude": 53.4808, "longitude": -2.2426},
    {"name": "Birmingham", "latitude": 52.4862, "longitude": -1.8904},
    {"name": "Edinburgh", "latitude": 55.9533, "longitude": -3.1883},
    {"name": "Cardiff", "latitude": 51.4816, "longitude": -3.1791},
]


def extract() -> list[tuple[str, dict]]:
    """Fetch data from Open-Meteo API for each city, save raw JSON, and return (city, payload) pairs."""
    raw_payloads = []
    now = datetime.now(timezone.utc)
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")

    folder_path = Path("data") / "raw" / date_folder
    folder_path.mkdir(parents=True, exist_ok=True)

    for city in CITIES:
        try:
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
            res = requests.get(BASE_URL, params=params, timeout=10)
            res.raise_for_status()
            payload = res.json()

            # Save raw JSON file with UTC timestamp
            clean_name = city["name"].lower().replace(" ", "_")
            file_path = folder_path / f"{clean_name}_{timestamp}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            raw_payloads.append((city["name"], payload))
            print(f"[EXTRACT] Saved raw payload for {city['name']}")

        except requests.RequestException as e:
            print(f"[ERROR] Failed extracting {city['name']}: {e}")

    return raw_payloads


def transform(raw: list[tuple[str, dict]]) -> pd.DataFrame:
    """Flatten JSON payloads, rename columns to snake_case with units, deduplicate, and add metadata."""
    dfs = []
    ingested_at = datetime.now(timezone.utc).isoformat()

    for city_name, payload in raw:
        df = pd.DataFrame(payload["hourly"])
        df["city"] = city_name
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    df_combined = pd.concat(dfs, ignore_index=True)

    # Rename columns to explicit snake_case names with measurement units
    rename_mapping = {
        "time": "observed_at",
        "temperature_2m": "temperature_c",
        "apparent_temperature": "feels_like_c",
        "relative_humidity_2m": "humidity_pct",
        "precipitation": "precipitation_mm",
        "wind_speed_10m": "wind_speed_kmh",
        "weather_code": "weather_code",
    }
    df_combined = df_combined.rename(columns=rename_mapping)
    df_combined["observed_at"] = pd.to_datetime(
        df_combined["observed_at"], format="mixed"
    )

    # Add ingestion metadata timestamp
    df_combined["ingested_at_utc"] = ingested_at

    # Deduplicate records on composite key (city, observed_at), retaining the latest record
    df_combined = df_combined.drop_duplicates(
        subset=["city", "observed_at"], keep="last"
    )

    # Enforce strict column ordering
    columns_order = [
        "city",
        "observed_at",
        "temperature_c",
        "feels_like_c",
        "humidity_pct",
        "precipitation_mm",
        "wind_speed_kmh",
        "weather_code",
        "ingested_at_utc",
    ]

    return df_combined[columns_order]


def canonicalize_observed_at(value: datetime | pd.Timestamp | str) -> str:
    """Serialize observation timestamps consistently for SQLite keys."""
    return pd.Timestamp(value).strftime("%Y-%m-%dT%H:%M:%S")


def load(df: pd.DataFrame, db_path: str = "weather.db") -> int:
    """Create SQLite table with primary key and insert rows idempotently using INSERT OR REPLACE."""
    if df.empty:
        print("[LOAD] No data to load.")
        return 0

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS weather_hourly (
        city            TEXT    NOT NULL,
        observed_at      TEXT    NOT NULL,
        temperature_c    REAL,
        feels_like_c      REAL,
        humidity_pct     INTEGER,
        precipitation_mm REAL,
        wind_speed_kmh   REAL,
        weather_code     INTEGER,
        ingested_at_utc  TEXT    NOT NULL,
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

    df_to_insert = df.copy()
    df_to_insert["observed_at"] = df_to_insert["observed_at"].map(
        canonicalize_observed_at
    )
    data_to_insert = [tuple(row) for row in df_to_insert.itertuples(index=False)]

    with closing(sqlite3.connect(db_path)) as conn, conn:
        cursor = conn.cursor()
        cursor.execute(create_table_sql)

        # Normalize legacy timestamp strings and merge rows that share the same hour.
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
        conn.commit()

    return len(data_to_insert)


def main():
    print("--- STARTING ETL PIPELINE V1 ---")
    raw_data = extract()
    transformed_df = transform(raw_data)
    rows_loaded = load(transformed_df)
    print(
        f"--- ETL COMPLETED: Processed and loaded {rows_loaded} rows into weather.db ---"
    )


if __name__ == "__main__":
    main()