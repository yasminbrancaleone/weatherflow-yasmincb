# WeatherFlow ETL Pipeline

## Project Goal

Build an automated data engineering pipeline that extracts live weather data for five UK cities from a REST API, stores timestamped raw JSON extractions, cleans and transforms the data with `pandas`, and loads the results into a SQLite database for SQL querying.

## How to Set Up

### Prerequisites

- Python 3.11 or newer
- Git

### Windows (PowerShell)

1. Clone the repository and move into the project directory:

   ```powershell
   git clone https://github.com/yasminbrancaleone/weatherflow-yasmincb.git
   cd weatherflow-yasmincb
   ```

2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the pinned project dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

## Author

Yasmin Cabrini Brancaleone
