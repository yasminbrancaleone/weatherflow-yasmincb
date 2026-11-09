# Reference Architecture Critique & Analysis

## 1. System Component Breakdown

| Component | Tool used | What it does in this project | Batch or streaming? |
| :--- | :--- | :--- | :--- |
| **Data source** | WeatherAPI, OpenWeatherMap; simulated station data is also mentioned | Python scripts fetch weather data from APIs, standardize formats, and save raw data locally. | Batch API polling |
| **Message broker** | Apache Kafka | Producer and consumer scripts pass weather messages through Kafka topics. | Streaming |
| **Processing** | Apache Spark (PySpark) | Processes data in batch mode and implements streaming analytics; the guide mentions derived metrics such as heat index and weather severity. | Batch and streaming (both are described) |
| **Orchestration** | Apache Airflow | Schedules and monitors the pipeline, with retries and scheduled or triggered runs described in the implementation guide. | Scheduled/triggered runs |
| **Storage** | File-based data lake; PostgreSQL for Airflow metadata | The docs describe raw and processed file zones. PostgreSQL is identified as Airflow's database, not as the weather-data store. | Batch/file output |
| **Serving** | Dashboard framework is inconsistent: Flask, Dash, and Streamlit are each mentioned | Presents weather visualizations; the documentation does not clearly establish the dashboard's data connection. | Not clearly specified |
| **Packaging** | Docker Compose | Starts and connects the documented services, including Kafka, Spark, Airflow, PostgreSQL, and a dashboard. | N/A (infrastructure) |

## 2. Architecture Critique & Risk Analysis

### What the Design Does Well
The design separates collection, transport, processing, storage, and visualization. Kafka decouples producers from consumers, while Spark supports batch and streaming workloads (`IMPLEMENTATION.md`, "Spark Processing"). Airflow scheduling and retries, together with Docker Compose, aim to coordinate and reproduce runs; the guides do not prove these work reliably.

### Identified Problems and Technical Risks
1. **Exposed credentials:** `README.md` publishes a literal WeatherAPI key in its prerequisites, setup example, and data-source description; `IMPLEMENTATION.md` repeats a key in its setup example. Remove credentials from tracked docs, use environment variables or a secret store, and rotate the exposed key. The README also gives the default Airflow login `admin` / `admin`, unsuitable beyond a local demo.
2. **Unclear serving path:** The docs describe file-based raw and processed zones, and identify PostgreSQL as Airflow's metadata database, but do not explain how the dashboard reads weather data. They also name Flask in the README overview, Dash/Flask in the implementation overview, and a Streamlit script in the README's local-run instructions. This makes the dashboard entry point and data connection uncertain.
3. **Safeguards are hard to verify:** The README lists a `tests/` directory but neither guide explains how to run tests or what success looks like. `IMPLEMENTATION.md` claims Airflow health checks and retries, yet gives no alert destination or procedure to confirm a failed run. This does not prove tests or monitoring are absent; their operation is not verifiable from these guides.

## 3. Essential vs. Overkill Evaluation (5-City Hourly Feed)

For five cities polled once an hour, an HTTP client, modest transformations, durable storage, and a scheduler are essential. A single Python job writing timestamped results to SQLite or a small PostgreSQL instance would be sufficient; add basic logs, retry handling, and a documented test command so failures can be detected and diagnosed.

Kafka and Spark are likely overkill at this scale: five hourly records are a small batch, so distributed streaming and processing add services to operate without a demonstrated throughput need. Airflow may still be useful if the workflow grows to multiple dependent jobs or requires a shared scheduling UI, but a full Dockerized stack is disproportionate for one hourly task. For the stated feed, start with a simple scheduled Python ETL and a lightweight database, then adopt the extra components only when scale or operational requirements justify them.
