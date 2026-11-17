# WeatherFlow Data Dictionary

## Dataset metadata

- **Source:** [Open-Meteo Forecast API](https://open-meteo.com/en/docs)
- **Refresh:** Each ETL run requests hourly data for the previous day and forecast.
- **Database table:** `weather_hourly` in `weather.db`
- **Processed output:** `data/processed/run_date=<YYYY-MM-DD>/part-<timestamp>.parquet`
- **Grain:** One row per city and observation timestamp.
- **Primary key:** `(city, observed_at_utc)`
- **Observation timezone:** The API is requested in UTC. The pipeline derives `Europe/London` timestamps for display and business dates.
- **Ingestion timezone:** UTC.
- **Units:** Source units and derived conversions are documented in the field definitions below.

## Loaded fields

| Column | SQLite type | Unit / format | Description | Source | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `city` | `TEXT` | City name | UK city associated with the hourly forecast. | Pipeline configuration | No; primary key |
| `observed_at_utc` | `TEXT` | ISO-8601 UTC timestamp | Start time of the hourly observation/forecast in UTC. This is the canonical observation key. | `hourly.time` | No; primary key |
| `observed_at_local` | `TEXT` | ISO-8601 Europe/London timestamp | UTC observation converted to Europe/London for display and business dates. | Derived from `observed_at_utc` | No |
| `temperature_c` | `REAL` | °C | Air temperature at 2 m above ground. | `hourly.temperature_2m` | Yes |
| `feels_like_c` | `REAL` | °C | Apparent temperature. | `hourly.apparent_temperature` | Yes |
| `humidity_pct` | `INTEGER` | % | Relative humidity at 2 m above ground. | `hourly.relative_humidity_2m` | Yes |
| `precipitation_mm` | `REAL` | mm | Precipitation accumulated during the hour. | `hourly.precipitation` | Yes |
| `wind_speed_kmh` | `REAL` | km/h | Wind speed at 10 m above ground. | `hourly.wind_speed_10m` | Yes |
| `weather_code` | `INTEGER` | WMO code | Weather condition code; see the [Open-Meteo documentation](https://open-meteo.com/en/docs). | `hourly.weather_code` | Yes |
| `description` | `TEXT` | Weather label | Human-readable description from the WMO reference table. | WMO reference | Yes |
| `category` | `TEXT` | Category | WMO category: `clear`, `cloudy`, `fog`, `drizzle`, `rain`, `snow`, or `storm`. | WMO reference | Yes |
| `temperature_f` | `REAL` | °F | Fahrenheit conversion: `temperature_c * 9/5 + 32`. | Derived | Yes |
| `wind_speed_ms` | `REAL` | m/s | Wind speed conversion: `wind_speed_kmh / 3.6`. | Derived | Yes |
| `beaufort_scale` | `INTEGER` | 0–12 | Beaufort wind-force scale derived from wind speed in m/s. | Derived | Yes |
| `is_daylight` | `BOOLEAN` | Boolean | Whether the observation is during daylight, based on the API's `is_day` value. | `hourly.is_day` | Yes |
| `outdoor_work_risk` | `TEXT` | `low`, `medium`, or `high` | `high` for Beaufort ≥ 7, storm/snow, or precipitation ≥ 4 mm; `medium` for Beaufort ≥ 5, precipitation ≥ 1 mm, or temperature ≤ 0 °C; otherwise `low`. | Derived | No |
| `ingested_at_utc` | `TEXT` | ISO-8601 UTC timestamp | Time when this pipeline run transformed the record. | Pipeline metadata | No |

The raw response also contains location metadata such as latitude, longitude, and elevation. Those fields are retained in the JSON files under `data/raw/`; they are not columns in `weather_hourly`.