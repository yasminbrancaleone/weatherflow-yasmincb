CREATE TABLE IF NOT EXISTS dim_city (
    city_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city_name TEXT NOT NULL UNIQUE,
    country TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_id INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    day_of_week TEXT NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_weather_hourly (
    city_id INTEGER NOT NULL,
    date_id INTEGER NOT NULL,
    observed_at_utc TIMESTAMPTZ NOT NULL,
    hour_local INTEGER NOT NULL CHECK (hour_local BETWEEN 0 AND 23),
    temperature_c DOUBLE PRECISION,
    feels_like_c DOUBLE PRECISION,
    humidity_pct INTEGER,
    precipitation_mm DOUBLE PRECISION,
    wind_speed_kmh DOUBLE PRECISION,
    wind_speed_ms DOUBLE PRECISION,
    weather_code INTEGER,
    description TEXT,
    category TEXT,
    temperature_f DOUBLE PRECISION,
    beaufort_scale INTEGER CHECK (
        beaufort_scale IS NULL OR beaufort_scale BETWEEN 0 AND 12
    ),
    is_daylight BOOLEAN,
    outdoor_work_risk TEXT NOT NULL
        CHECK (outdoor_work_risk IN ('low', 'medium', 'high')),
    source TEXT NOT NULL,
    ingested_at_utc TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (city_id, observed_at_utc, source),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id),
    FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    alert_key TEXT PRIMARY KEY,
    sent_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_key TEXT NOT NULL UNIQUE REFERENCES alerts_sent(alert_key),
    alert_type TEXT NOT NULL CHECK (
        alert_type IN ('risk', 'pipeline_failure')
    ),
    message TEXT NOT NULL,
    city_name TEXT,
    period_start_utc TIMESTAMPTZ,
    period_end_utc TIMESTAMPTZ,
    dag_id TEXT,
    task_id TEXT,
    try_number INTEGER CHECK (try_number IS NULL OR try_number > 0),
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
