# Week 3 Reflection

## What I built

I added WeatherAPI.com as a second source, moved warehouse storage to
PostgreSQL in Docker, and containerized the pipeline. I added an hourly Airflow
DAG, GitHub Actions CI, a Streamlit dashboard, and deduplicated weather-risk
and pipeline-failure alerts. Three ADRs record the choices for the shared
network, source disagreements, and alert fallback.

## Production engineering lessons

- Environment variables keep API keys and database credentials out of source
  code. The committed `.env.example` documents the required settings without
  containing real secrets.
- Container service names, rather than `localhost`, are the right connection
  address between Compose services.
- Airflow's metadata database and the weather warehouse have different
  responsibilities and should remain separate.
- Exit codes let Airflow and other callers detect failed work; retries and
  failure callbacks make that failure visible.
- Idempotency applies to notifications as well as data loads: a unique alert
  key prevents the same risk period or task run from being recorded twice.
- A dashboard should show freshness and source disagreement, not just charts;
  stale data must not look like a current safe forecast.

## Challenges and decisions

Airflow runs in a separate Compose project, so the scheduler and worker need
explicit access to the warehouse network. The dashboard keeps both source
readings visible because neither provider is treated as authoritative. No real
webhook was configured, so alerts are persisted in the warehouse and logs;
the limitations and alternatives are documented in ADR 0003.

The local dashboard could start, but the root `.env` and warehouse were not
available during this validation. Consequently I could verify the Streamlit
server and page shell, but not load live warehouse rows or verify the full
five-city, two-source presentation locally.

## Skills tracker

| Skill | Progress |
|---|---|
| Secrets and environment-based configuration | Practiced |
| PostgreSQL schema and idempotent transactions | Practiced |
| Docker Compose networking | Practiced |
| Airflow scheduling, retries, and callbacks | Implemented; live callback verification remains |
| GitHub Actions and coverage gate | Implemented; deliberate red-to-green PR demonstration remains |
| Streamlit, alerts, and ADRs | Implemented; live warehouse verification remains |

## Validation evidence and remaining checks

- `.\.venv\Scripts\python.exe -m pytest -q`: 70 passed, 4 skipped. The skips
  include PostgreSQL integration tests because `DATABASE_URL` was not set.
- `git diff --check`: passed for the implementation changes.
- `Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://localhost:8501/_stcore/health`:
  returned HTTP 200 with `ok`. The dashboard page returned HTTP 200 and rendered
  its title, then showed a configuration error because `DATABASE_URL` was
  unavailable.
- A run with a configured warehouse is still needed to verify the dashboard
  data, PostgreSQL alert idempotency, and the Airflow failure callback end to
  end. Three consecutive scheduled Airflow runs and the deliberate failing-PR
  demonstration also remain external acceptance checks.
