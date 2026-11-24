# WeatherFlow ETL Pipeline

WeatherFlow is a learning project that collects hourly weather data for five UK cities from the free [Open-Meteo Forecast API](https://open-meteo.com/en/docs) and [WeatherAPI.com](https://www.weatherapi.com/), saves the original API responses, transforms them with pandas, and loads them into SQLite for SQL analysis.

**GitHub repository:** [yasminbrancaleone/weatherflow-yasmincb](https://github.com/yasminbrancaleone/weatherflow-yasmincb)

## Pipeline

1. **Extract:** Request hourly forecasts from Open-Meteo and WeatherAPI.com for London, Manchester, Birmingham, Edinburgh, and Cardiff.
2. **Land raw data:** Save each complete API response as JSON under `data/raw/<UTC-date>/`.
3. **Transform and validate:** Normalize both providers to the canonical hourly columns, apply each provider's weather-code reference, deduplicate by `(city, observed_at_utc, source)`, and warn when same-city/hour temperatures differ by more than the configured 3 °C threshold.
4. **Process:** Write the transformed observations as Parquet under `data/processed/run_date=<UTC-date>/`.
5. **Load:** Store the observations in `weather.db`. The `(city, observed_at_utc, source)` primary key makes repeated runs idempotent while keeping both providers' records.

Open-Meteo does not require a key. WeatherAPI.com uses `WEATHERAPI_KEY` from `.env`; the key is never written to raw payload files or application logs. An internet connection is required to run extraction.

## Project Structure

```text
weatherflow-yasmincb/
├── data/raw/                 # Date-partitioned raw API responses (not tracked by Git)
├── data/processed/           # Partitioned Parquet outputs (not tracked by Git)
├── config.yaml               # API, city, and output path configuration
├── .env.example              # Environment variable template (fake values only)
├── docs/
│   ├── data_dictionary.md    # Fields, units, and dataset grain
│   ├── reference_architecture.md
│   ├── reference_critique.md
│   └── reflections/
│       └── week_1.md         # Week 1 learning reflection
├── src/weatherflow/          # Installable WeatherFlow package
│   ├── config.py
│   ├── extract.py
│   ├── transform.py
│   ├── load.py
│   ├── output.py
│   └── pipeline.py
├── notebooks/01_explore.ipynb # Exploration and profiling of raw data
├── sql/week1_queries.sql     # Example analytical queries
├── pyproject.toml
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
python -m pip install -e .
Copy-Item .env.example .env
```

Edit `.env` and replace the example value with your own WeatherAPI.com key. The `.env` file is ignored by Git.

## Run Tests

Run the complete unit and integration test suite with coverage:

```powershell
pytest -v --cov=src --cov-report=term-missing
```

Latest validation summary:

```text
43 passed
TOTAL                            551    118    79%
```

## Run the Pipeline

From any directory, with the virtual environment active and the package installed:

```powershell
python -m weatherflow run
```

The default runs both sources. To run only one:

```powershell
python -m weatherflow run --source open_meteo
python -m weatherflow run --source weatherapi
```

Run a 30-day historical backfill ending five days before today:

```powershell
python -m weatherflow backfill --days 30
```

The backfill can also use explicit inclusive dates:

```powershell
python -m weatherflow backfill --start-date 2026-10-01 --end-date 2026-10-30
```

The command reads API settings, cities, and output paths from `config.yaml`. Example
output (the timestamp and row count can vary):

```text
2026-11-17 10:00:00 | INFO | weatherflow.pipeline | Starting weather pipeline.
2026-11-17 10:00:05 | INFO | weatherflow.load | Loaded 240 weather observations into ...\weather.db.
2026-11-17 10:00:05 | INFO | weatherflow.pipeline | Weather pipeline completed with 240 loaded rows.
```

The raw files, processed Parquet files, and SQLite database are local outputs and are excluded from Git. Re-running the pipeline refreshes rows with the same city and observation time instead of creating duplicate keys.

## Query the SQLite Database

The example queries are in [`sql/week1_queries.sql`](sql/week1_queries.sql). To run them from the repository root using Python's built-in SQLite module:

```powershell
python -c "import sqlite3; conn = sqlite3.connect('weather.db'); cursor = conn.cursor(); [print('\n--- Query Result ---', *cursor.execute(q).fetchall(), sep='\n') for q in open('sql/week1_queries.sql').read().split(';') if q.strip()]"
```

This command also works when launched through a VS Code SQLite extension configured to run Python commands. The second query interprets “yesterday” using the computer's local timezone; the API observations use UTC.

## Other Project Materials

- [`notebooks/01_explore.ipynb`](notebooks/01_explore.ipynb) profiles and visualizes the raw hourly data.
- [`docs/data_dictionary.md`](docs/data_dictionary.md) documents the explored dataset's columns and units.
- [`src/weatherflow/reference/weatherapi_codes.csv`](src/weatherflow/reference/weatherapi_codes.csv) maps WeatherAPI condition codes to the project's weather categories.
- [`sql/week1_queries.sql`](sql/week1_queries.sql) contains queries for coverage, yesterday's average temperature, and the five windiest observations.

## Author

Yasmin Cabrini Brancaleone
