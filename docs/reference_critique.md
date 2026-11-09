# Reference Architecture Critique & Analysis

## 1. System Component Breakdown

| Component | Tool used | What it does in this project | Batch or streaming? |
| :--- | :--- | :--- | :--- |
| **Data source** | WeatherAPI, OpenWeatherMap | Fetches live JSON weather payloads via HTTP endpoints. | Batch (Polled API calls) |
| **Message broker** | Apache Kafka | Ingests and queues raw JSON payloads into topic streams to decouple ingestion from processing. | Streaming |
| **Processing** | Apache Spark (PySpark) | Parses JSON streams, standardizes schemas, cleans missing data, and aggregates weather metrics. | Streaming |
| **Orchestration** | Apache Airflow | Triggers scheduled DAG execution, coordinates service dependencies, and manages workflow state. | Batch |
| **Storage** | PostgreSQL | Stores structured, transformed hourly weather data in relational tables for persistence. | Batch |
| **Serving** | Grafana / Streamlit | Queries PostgreSQL to present visual time-series charts and key weather metrics to end users. | Batch |
| **Packaging** | Docker Compose | Provisions and connects isolated containers for Kafka, Spark, Postgres, Airflow, and Grafana. | N/A (Infrastructure) |