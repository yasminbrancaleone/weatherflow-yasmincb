# WeatherFlow ETL Pipeline

[![CI](https://github.com/yasminbrancaleone/weatherflow-yasmincb/actions/workflows/ci.yml/badge.svg)](https://github.com/yasminbrancaleone/weatherflow-yasmincb/actions/workflows/ci.yml)

WeatherFlow is a learning project that collects hourly weather data for five UK cities from the free [Open-Meteo Forecast API](https://open-meteo.com/en/docs) and [WeatherAPI.com](https://www.weatherapi.com/), saves the original API responses, transforms them with pandas, and loads them into a PostgreSQL 18 warehouse for SQL analysis. SQLite remains available as a local fallback when `DATABASE_URL` is unset.

**GitHub repository:** [yasminbrancaleone/weatherflow-yasmincb](https://github.com/yasminbrancaleone/weatherflow-yasmincb)

## Pipeline

1. **Extract:** Request hourly forecasts from Open-Meteo and WeatherAPI.com for London, Manchester, Birmingham, Edinburgh, and Cardiff.
2. **Land raw data:** Save each complete API response as JSON under `data/raw/<UTC-date>/`.
3. **Transform and validate:** Normalize both providers to the canonical hourly columns, apply each provider's weather-code reference, deduplicate by `(city, observed_at_utc, source)`, and warn when same-city/hour temperatures differ by more than the configured 3 °C threshold.
4. **Process:** Write the transformed observations as Parquet under `data/processed/run_date=<UTC-date>/`.
5. **Load:** Upsert observations into PostgreSQL's `fact_weather_hourly` table when `DATABASE_URL` is set. The `(city_id, observed_at_utc, source)` primary key makes repeated runs idempotent while keeping both providers' records. The dimensions and facts are loaded in one transaction.

Open-Meteo does not require a key. WeatherAPI.com uses `WEATHERAPI_KEY` from `.env`; the key is never written to raw payload files or application logs. An internet connection is required to run extraction.

## Project Structure

```text
weatherflow-yasmincb/
├── data/raw/                 # Date-partitioned raw API responses (not tracked by Git)
├── data/processed/           # Partitioned Parquet outputs (not tracked by Git)
├── config.yaml               # API, city, and output path configuration
├── .env.example              # Environment variable template (fake values only)
├── Dockerfile                 # Non-root Python pipeline image
├── .dockerignore              # Excludes secrets, local data, and development files
├── docker-compose.yml         # PostgreSQL warehouse and pipeline services
├── orchestration/
│   ├── dags/
│   │   └── weatherflow_hourly.py
│   ├── docker-compose.yaml    # Official Airflow 3.4.0 learning setup
│   └── Dockerfile             # Airflow image with WeatherFlow installed
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
├── sql/
│   ├── analysis_queries.sql   # PostgreSQL analytical queries
│   └── schema_postgres.sql    # Warehouse star schema
├── .github/workflows/ci.yml   # Unit and PostgreSQL integration CI
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── weather.db               # SQLite output (not tracked by Git)
```

## Setup

### Prerequisites

- Python 3.11 or newer
- Git
- Docker Desktop with Docker Compose
- Internet access for the Open-Meteo API

### Windows (PowerShell)

```powershell
git clone https://github.com/yasminbrancaleone/weatherflow-yasmincb.git
cd weatherflow-yasmincb
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install -e .
Copy-Item .env.example .env
```

Edit `.env`: set your WeatherAPI.com key and replace the sample PostgreSQL password.
Keep `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `DATABASE_URL` consistent;
`DATABASE_URL` should connect to `localhost:5433`. Use a URL-safe PostgreSQL password
(letters, numbers, underscores, or hyphens) because Compose also builds the container's
`DATABASE_URL` from it. Then start the warehouse:

```powershell
docker compose up -d warehouse
docker compose ps
```

Wait until `warehouse` reports `healthy`. The named volume preserves warehouse data
across `docker compose down` and `docker compose up`; `docker compose down -v` also
deletes that data. The `.env` file is ignored by Git.

### Run the pipeline in Docker

The Docker workflow does not require a local Python installation. After editing
`.env` as described above, build the image and run the pipeline:

```powershell
docker compose build pipeline
docker compose run --rm pipeline run
```

Compose waits for the warehouse health check before starting the pipeline. Inside
the Compose network, the pipeline connects to `warehouse:5432`; from your computer,
`DATABASE_URL` in `.env` continues to use `localhost:5433`. The `./data` directory
and DQ reports are mounted from the host, so generated files remain available after
the one-off pipeline container is removed.

Run a seven-day backfill or select one source with:

```powershell
docker compose run --rm pipeline backfill --days 7
docker compose run --rm pipeline run --source open_meteo
docker compose run --rm pipeline run --source weatherapi
```

The container's exit code is returned to the calling shell. For example, a missing
WeatherAPI key causes a non-zero exit code. Use `docker compose down` to stop the
warehouse while retaining its named data volume.

## Run the hourly Airflow DAG

Airflow runs as a separate Docker Compose project with its own metadata database
and Redis broker. The weather warehouse remains the separate `warehouse` service.
Docker Desktop should have at least 4 GB of memory available.

Create `orchestration/.env` from `orchestration/.env.example` if it does not exist:

```powershell
if (-not (Test-Path orchestration/.env)) {
    Copy-Item orchestration/.env.example orchestration/.env
}
```

Set a local WeatherAPI key and PostgreSQL credentials in the root `.env` as in the
Docker setup above. Start the warehouse first so it creates the shared `weatherflow`
network, then build and initialize Airflow:

```powershell
docker compose up -d warehouse
docker compose --env-file .env --env-file orchestration/.env -f orchestration/docker-compose.yaml build
docker compose --env-file .env --env-file orchestration/.env -f orchestration/docker-compose.yaml up airflow-init
docker compose --env-file .env --env-file orchestration/.env -f orchestration/docker-compose.yaml up -d
```

The DAG is in [`orchestration/dags/weatherflow_hourly.py`](orchestration/dags/weatherflow_hourly.py)
and runs both sources hourly before checking recent high-risk observations. Open
<http://localhost:8080> and unpause `weatherflow_hourly`; the local Airflow quick
start uses `airflow` / `airflow` for its UI login. Source tasks run in Airflow's
worker, where `WEATHERAPI_KEY` and the warehouse `DATABASE_URL` are passed from
the root `.env`. A task failure is retried twice, then logged by the failure
callback. The local Airflow Compose setup is for learning, not production.

Stop only the Airflow project with:

```powershell
docker compose --env-file .env --env-file orchestration/.env -f orchestration/docker-compose.yaml down
```

## Run Tests

The CI workflow runs on every push and pull request. It uses a temporary PostgreSQL
18 service and enforces at least 70% coverage. No WeatherAPI key or live API request
is needed by the tests.

To run tests offline without PostgreSQL, leave `DATABASE_URL` unset. The PostgreSQL
integration tests will be skipped:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
pytest --cov=src --cov-report=term-missing --cov-fail-under=70
```

To run the PostgreSQL integration tests locally, start the warehouse and set its
connection URL before running the same command:

```powershell
$env:DATABASE_URL = "postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@localhost:5433/<POSTGRES_DB>"
pytest --cov=src --cov-report=term-missing --cov-fail-under=70
Remove-Item Env:DATABASE_URL
```

Latest local validation: 67 passed with PostgreSQL 18 enabled (84.60% coverage);
without `DATABASE_URL`, 64 passed and the 3 PostgreSQL integration tests were skipped
(78.24% coverage). URL-encode special characters in the connection URL password.

## Run the Pipeline

With the virtual environment active and the package installed, run locally with:

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

The command reads API settings, cities, and output paths from `config.yaml`, and the
warehouse connection from `.env`. Example output (timestamps and row counts vary):

```text
2026-11-17 10:00:00 | INFO | weatherflow.pipeline | Starting weather pipeline.
2026-11-17 10:00:05 | INFO | weatherflow.postgres | PostgreSQL load from source open_meteo_forecast: 120 new rows, 0 updated rows.
2026-11-17 10:00:05 | INFO | weatherflow.pipeline | Weather pipeline completed: 120 new rows, 0 updated rows.
```

The raw files, processed Parquet files, and local SQLite database are excluded from
Git. Re-running the pipeline refreshes rows with the same city, observation time,
and source instead of creating duplicate keys.

## Query the PostgreSQL Warehouse

The five PostgreSQL analysis queries are in [`sql/analysis_queries.sql`](sql/analysis_queries.sql).
Run them from the repository root with the project's psycopg dependency:

```powershell
python -c "from weatherflow.config import get_database_url; import psycopg; conn = psycopg.connect(get_database_url()); [print('\n--- Query Result ---', *conn.execute(q).fetchall(), sep='\n') for q in open('sql/analysis_queries.sql', encoding='utf-8').read().split(';') if q.strip()]; conn.close()"
```

`get_database_url()` reads `DATABASE_URL` from `.env`. Start the warehouse and run
the pipeline at least once before querying it.

## Other Project Materials

- [`notebooks/01_explore.ipynb`](notebooks/01_explore.ipynb) profiles and visualizes the raw hourly data.
- [`docs/data_dictionary.md`](docs/data_dictionary.md) documents the explored dataset's columns and units.
- [`src/weatherflow/reference/weatherapi_codes.csv`](src/weatherflow/reference/weatherapi_codes.csv) maps WeatherAPI condition codes to the project's weather categories.
- [`sql/analysis_queries.sql`](sql/analysis_queries.sql) contains five PostgreSQL queries for data coverage, latest-date temperature, strongest winds, and weekday/weekend wind comparisons.

## Author

Yasmin Cabrini Brancaleone
