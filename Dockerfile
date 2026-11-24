FROM python:3.11-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .

COPY config.yaml ./config.yaml
COPY sql/schema_postgres.sql ./sql/schema_postgres.sql

RUN groupadd --gid 1000 weatherflow \
    && useradd --uid 1000 --gid weatherflow --create-home --shell /usr/sbin/nologin weatherflow \
    && mkdir -p /app/data /app/docs/dq_reports \
    && chown -R weatherflow:weatherflow /app

USER weatherflow

ENTRYPOINT ["python", "-m", "weatherflow"]
CMD ["run"]
