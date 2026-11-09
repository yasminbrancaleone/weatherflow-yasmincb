# WeatherFlow ETL Pipeline

## Goal
Build an automated data engineering pipeline to extract live weather data for 5 UK cities from a REST API, store raw JSON extractions with timestamping, clean and transform the dataset using `pandas`, and load the final output into a SQLite database for SQL querying.

## How to Set Up (Windows)

1. **Clone the repository:**
   ```cmd
   git clone [https://github.com/](https://github.com/)<your-user>/weatherflow-yasmin-brancaleone.git
   cd weatherflow-yasmin-brancaleone

2. **Create and activate a virtual environment:**
    ```cmd
    python -m venv .venv
    .venv\Scripts\activate

3. **Install dependencies:**
    ```cmd
    pip install -r requirements.txt

## Author

Yasmin Cabrini Brancaleone