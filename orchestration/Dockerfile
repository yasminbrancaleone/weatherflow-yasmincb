FROM apache/airflow:3.4.0

WORKDIR /opt/airflow
USER airflow

COPY --chown=airflow:root pyproject.toml ./
COPY --chown=airflow:root src/ ./src/
COPY --chown=airflow:root config.yaml ./config.yaml
COPY --chown=airflow:root sql/schema_postgres.sql ./sql/schema_postgres.sql

ENV PYTHONPATH=/opt/airflow/src

RUN pip install --no-cache-dir "apache-airflow==3.4.0" .
