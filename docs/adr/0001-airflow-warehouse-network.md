# ADR 0001: Airflow and warehouse network

- Status: Accepted
- Date: 2026-11-25

## Context

Airflow and the WeatherFlow warehouse run as separate Docker Compose projects.
Airflow also needs its own metadata database, while the pipeline tasks and
failure callback need to reach the business-data warehouse.

## Decision

Keep Airflow's metadata PostgreSQL separate from the WeatherFlow warehouse.
Attach the Airflow scheduler and worker to the shared external `weatherflow`
Docker network and configure `DATABASE_URL` with the warehouse service name
`warehouse:5432`.

## Consequences

The pipeline and callback can reach the warehouse without using container-local
`localhost`. Airflow metadata stays independent from weather facts. The root
`.env` must supply the warehouse credentials to the scheduler and worker.

## Alternatives considered

- Reuse Airflow's metadata database for weather facts: rejected to keep
  orchestration state separate from business data.
- Connect to `localhost` from Airflow containers: rejected because it resolves
  to the Airflow container itself.
- Copy data between the warehouse and Airflow's database: rejected as duplicate
  storage with unnecessary synchronization.
