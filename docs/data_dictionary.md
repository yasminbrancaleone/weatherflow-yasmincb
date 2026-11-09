# WeatherFlow Data Dictionary

## Metadata
* **Source:** [Open-Meteo Weather Forecast API](https://open-meteo.com/en/docs)
* **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
* **Refresh Frequency:** Hourly
* **Dataset Grain:** One row per city per hour

---

## Field Specifications

| Column | Type | Unit | Description | Example | Nullable? | Source Field |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `time` | string (ISO-8601) | Europe/London local time | Timestamp marking the start of the hourly observation window; loaded as text and converted to datetime only for plotting | `2026-11-10T14:00` | No | `hourly.time` |
| `city` | string | N/A | Name of the target UK city | `London` | No | Injected pipeline metadata |
| `latitude` | float | Decimal Degrees | Geographic latitude coordinate of the location | `51.5085` | No | `latitude` |
| `longitude` | float | Decimal Degrees | Geographic longitude coordinate of the location | `-0.1257` | No | `longitude` |
| `elevation` | float | Meters | Ground elevation above sea level; defaults to `0.0` if absent from the API payload | `25.0` | No (defaults to `0.0` if absent) | `elevation` (default: `0.0`) |
| `temperature_2m` | float | °C | Air temperature 2 meters above ground level | `8.4` | Yes | `hourly.temperature_2m` |
| `relative_humidity_2m` | integer | % | Relative humidity 2 meters above ground level | `82` | Yes | `hourly.relative_humidity_2m` |
| `apparent_temperature` | float | °C | Perceived "feels-like" temperature combining wind and humidity | `6.1` | Yes | `hourly.apparent_temperature` |
| `precipitation` | float | mm | Liquid water equivalent precipitation accumulated during the hour | `0.0` | Yes | `hourly.precipitation` |
| `wind_speed_10m` | float | km/h | Wind speed 10 meters above ground level | `14.2` | Yes | `hourly.wind_speed_10m` |
| `weather_code` | integer | WMO Code | World Meteorological Organization numerical code for weather condition | `3` | Yes | `hourly.weather_code` |