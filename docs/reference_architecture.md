# WeatherFlow Reference Architecture

This diagram illustrates the data flow of the reference pipeline (`WeatherFlow-DataEngineering`), mapping each stage to **E**xtract, **T**ransform, and **L**oad operations.

```mermaid
flowchart LR
    subgraph E [EXTRACT STAGE]
        API[Weather APIs: WeatherAPI / OpenWeatherMap]
        PROD[Kafka Producer Script]
        API -->|1. REST HTTP Requests| PROD
    end

    subgraph T [TRANSFORM STAGE]
        KAFKA[(Kafka Topic: weather-raw-data)]
        SPARK[PySpark Streaming Processor]
        PROD -->|2. Publish Raw JSON| KAFKA
        KAFKA -->|3. Consume Stream| SPARK
    end

    subgraph L [LOAD & SERVE STAGE]
        PG[(PostgreSQL Database)]
        DASH[Grafana / Streamlit Dashboard]
        SPARK -->|4. Write Transformed Tables| PG
        PG -->|5. SQL Queries| DASH
    end

    ORCH[Apache Airflow] -. Orchestrates .-> PROD
    ORCH -. Orchestrates .-> SPARK
    DOCKER[Docker Compose] -. Containerizes Environment .-> E
    DOCKER -. Containerizes Environment .-> T
    DOCKER -. Containerizes Environment .-> L