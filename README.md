# WeatherFlow ETL Pipeline

WeatherFlow is a learning project that collects hourly weather data for five UK cities from the free [Open-Meteo Forecast API](https://open-meteo.com/en/docs), saves the original API responses, transforms them with pandas, and loads them into SQLite for SQL analysis.

## Pipeline

1. **Extract:** Request the previous day and forecast from Open-Meteo for London, Manchester, Birmingham, Edinburgh, and Cardiff.
2. **Land raw data:** Save each complete API response as JSON under `data/raw/<UTC-date>/`.
3. **Transform:** Flatten the hourly observations, convert `observed_at` to a pandas datetime, standardize column names and units, add the UTC ingestion timestamp, and remove duplicate `(city, observed_at)` rows.
4. **Load:** Upsert rows into `weather.db` in the `weather_hourly` table. The `(city, observed_at)` primary key makes repeated runs replace existing observations.

The API does not require a key. An internet connection is required to run the extraction.

## Project Structure

```text
weatherflow-yasmincb/
├── data/raw/                 # Date-partitioned raw API responses (not tracked by Git)
├── docs/
│   ├── data_dictionary.md    # Fields, units, and dataset grain
│   ├── reference_architecture.md
│   └── reference_critique.md
├── notebooks/01_explore.ipynb # Exploration and profiling of raw data
├── sql/week1_queries.sql     # Example analytical queries
├── etl_v1.py                # End-to-end Extract, Transform, Load pipeline
├── extract.py               # Standalone raw API extraction exercise
├── requirements.txt
└── weather.db               # SQLite output (not tracked by Git)
```

## Setup

### Prerequisites

- Python 3.11 or newer
- Git
- Internet access for the Open-Meteo API

### Windows (PowerShell)

```powershell
git clone https://github.com/yasminbrancaleone/weatherflow-yasmincb.git
cd weatherflow-yasmincb
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run the Pipeline

From the repository root, with the virtual environment active:

```powershell
python etl_v1.py
```

Example output (the timestamp and row count can vary):

```text
--- STARTING ETL PIPELINE V1 ---
[EXTRACT] Saved raw payload for London
[EXTRACT] Saved raw payload for Manchester
[EXTRACT] Saved raw payload for Birmingham
[EXTRACT] Saved raw payload for Edinburgh
[EXTRACT] Saved raw payload for Cardiff
--- ETL COMPLETED: Processed and loaded 240 rows into weather.db ---
```

The raw files and SQLite database are local outputs and are excluded from Git. Re-running the pipeline refreshes rows with the same city and observation time instead of creating duplicate keys.

## Query the SQLite Database

The example queries are in [`sql/week1_queries.sql`](sql/week1_queries.sql). To run them from the repository root using Python's built-in SQLite module:

```powershell
python -c "import sqlite3; conn = sqlite3.connect('weather.db'); cursor = conn.cursor(); [print('\n--- Query Result ---', *cursor.execute(q).fetchall(), sep='\n') for q in open('sql/week1_queries.sql').read().split(';') if q.strip()]"
```

This command also works when launched through a VS Code SQLite extension configured to run Python commands. The second query interprets “yesterday” using the computer's local timezone; the API observations use `Europe/London`.

## Other Project Materials

- [`notebooks/01_explore.ipynb`](notebooks/01_explore.ipynb) profiles and visualizes the raw hourly data.
- [`docs/data_dictionary.md`](docs/data_dictionary.md) documents the explored dataset's columns and units.
- [`sql/week1_queries.sql`](sql/week1_queries.sql) contains queries for coverage, yesterday's average temperature, and the five windiest observations.

## Author

Yasmin Cabrini Brancaleone
