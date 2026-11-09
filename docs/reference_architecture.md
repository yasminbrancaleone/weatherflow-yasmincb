# WeatherFlow Reference Architecture

This diagram summarizes the flow described in the reference repository's `README.md` and `IMPLEMENTATION.md`. The dashboard framework and the exact connection between the data lake and dashboard are not consistently specified in those documents; the inferred serving link is marked accordingly.

```mermaid
flowchart LR
    subgraph E [EXTRACT STAGE]
        API[Weather APIs: WeatherAPI / OpenWeatherMap]
        PROD[Python API scripts / Kafka producer]
        API -->|1. REST HTTP Requests| PROD
    end

    subgraph T [TRANSFORM STAGE]
        KAFKA[(Kafka: raw weather stream)]
        SPARK[Apache Spark: batch processing and streaming analytics]
        PROD -->|2. Publish weather data| KAFKA
        KAFKA -->|3. Consume messages| SPARK
    end

    subgraph L [LOAD STAGE]
        LAKE[(File-based data lake: raw / processed)]
        SPARK -->|4. Store processed data| LAKE
    end

    DASH[Dashboard: Flask / Dash; README also mentions Streamlit]
    LAKE -.->|5. Serving link inferred; framework and connection are unclear| DASH
    AIRFLOW[Apache Airflow] -. Schedules and monitors .-> PROD
    AIRFLOW -. Schedules and monitors .-> SPARK
    PG[(PostgreSQL: Airflow metadata)]
    AIRFLOW -. Metadata database .-> PG
    DOCKER[Docker Compose] -. Packages services .-> PROD
    DOCKER -. Packages services .-> KAFKA
    DOCKER -. Packages services .-> SPARK
    DOCKER -. Packages services .-> AIRFLOW
    DOCKER -. Packages services .-> PG
    DOCKER -. Packages services .-> DASH