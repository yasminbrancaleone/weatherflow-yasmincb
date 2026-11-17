# WeatherFlow Star Schema

## Grain

One row per city, per hour, per source.

Each fact row represents one hourly weather observation from a configured city
and a specific data source. The composite primary key is
`(city_id, observed_at_utc, source)`.

## Date convention

`date_id` uses the local Europe/London calendar date. It is derived from
`observed_at_local`, not `observed_at_utc`. This ensures that a UTC reading near
midnight is assigned to the correct UK business date.

The `dim_date.date_id` value is stored as an integer in `YYYYMMDD` format.

## Entity relationship diagram

```mermaid
erDiagram
    DIM_CITY {
        integer city_id PK
        text city_name UK
        text country
        real latitude
        real longitude
    }

    DIM_DATE {
        integer date_id PK
        text full_date UK
        text day_of_week
        integer is_weekend
        integer month
        integer year
    }

    FACT_WEATHER_HOURLY {
        integer city_id FK
        integer date_id FK
        text observed_at_utc
        integer hour_local
        real temperature_c
        real feels_like_c
        integer humidity_pct
        real precipitation_mm
        real wind_speed_kmh
        real wind_speed_ms
        integer weather_code
        text description
        text category
        real temperature_f
        integer beaufort_scale
        integer is_daylight
        text outdoor_work_risk
        text source
        text ingested_at_utc
    }

    DIM_CITY ||--o{ FACT_WEATHER_HOURLY : contains
    DIM_DATE ||--o{ FACT_WEATHER_HOURLY : groups
```

## Natural and surrogate keys

- `city_name` is the natural city key and is used in configuration and validation.
- `city_id` is the surrogate key assigned to `dim_city` by SQLite.
- `date_id` is a business-safe integer surrogate derived from the local date.
- `source` distinguishes measurements produced by different weather sources.
