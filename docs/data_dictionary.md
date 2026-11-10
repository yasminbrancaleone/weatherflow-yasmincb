# WeatherFlow Data Dictionary

## Dataset metadata

- **Source:** [Open-Meteo Forecast API](https://open-meteo.com/en/docs)
- **Refresh:** Each ETL run requests hourly data for the previous day and forecast.
- **Database table:** `weather_hourly` in `weather.db`
- **Grain:** One row per city and observation timestamp.
- **Primary key:** `(city, observed_at)`
- **Observation timezone:** `Europe/London`, as returned by the API. The timestamp is stored as local wall time without a timezone offset.
- **Ingestion timezone:** UTC.
- **Units:** Open-Meteo's response units are used; the pipeline renames the fields but does not convert the values.

## Loaded fields

| Column | SQLite type | Unit / format | Description | Source | Nullable |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `city` | `TEXT` | City name | UK city associated with the hourly forecast. | Pipeline configuration | No; primary key |
| `observed_at` | `TEXT` | `YYYY-MM-DDTHH:MM:SS`, Europe/London local time | Start time of the hourly observation/forecast. Stored in a canonical format so equivalent timestamps use the same key. | `hourly.time` | No; primary key |
| `temperature_c` | `REAL` | °C | Air temperature at 2 m above ground. | `hourly.temperature_2m` | Yes |
| `feels_like_c` | `REAL` | °C | Apparent temperature. | `hourly.apparent_temperature` | Yes |
| `humidity_pct` | `INTEGER` | % | Relative humidity at 2 m above ground. | `hourly.relative_humidity_2m` | Yes |
| `precipitation_mm` | `REAL` | mm | Precipitation accumulated during the hour. | `hourly.precipitation` | Yes |
| `wind_speed_kmh` | `REAL` | km/h | Wind speed at 10 m above ground. | `hourly.wind_speed_10m` | Yes |
| `weather_code` | `INTEGER` | WMO code | Weather condition code; see the [Open-Meteo documentation](https://open-meteo.com/en/docs). | `hourly.weather_code` | Yes |
| `ingested_at_utc` | `TEXT` | ISO-8601 UTC timestamp | Time when this pipeline run transformed the record. | Pipeline metadata | No |

The raw response also contains location metadata such as latitude, longitude, and elevation. Those fields are retained in the JSON files under `data/raw/`; they are not columns in `weather_hourly`.