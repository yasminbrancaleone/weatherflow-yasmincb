-- 1. Record coverage and observation range by city.
-- Business question: How much data and how much time coverage are available per city?
SELECT
    city.city_name,
    COUNT(*) AS total_records,
    MIN(fact.observed_at_utc) AS earliest_observation,
    MAX(fact.observed_at_utc) AS latest_observation
FROM fact_weather_hourly AS fact
JOIN dim_city AS city
    ON city.city_id = fact.city_id
GROUP BY city.city_name
ORDER BY city.city_name;

-- 2. Average temperature per city for the latest local date in the fact table.
-- Business question: What was the average temperature profile for the latest UK date?
SELECT
    city.city_name,
    ROUND(AVG(fact.temperature_c)::numeric, 2) AS avg_temperature_c
FROM fact_weather_hourly AS fact
JOIN dim_city AS city
    ON city.city_id = fact.city_id
JOIN dim_date AS date
    ON date.date_id = fact.date_id
WHERE date.full_date = (
    SELECT MAX(full_date)
    FROM dim_date
    WHERE date_id IN (
        SELECT date_id
        FROM fact_weather_hourly
    )
)
GROUP BY city.city_name
ORDER BY avg_temperature_c DESC;

-- 3. Five windiest observations across all cities.
-- Business question: Where and when did the strongest wind observations occur?
SELECT
    city.city_name,
    fact.observed_at_utc,
    fact.wind_speed_kmh,
    fact.weather_code
FROM fact_weather_hourly AS fact
JOIN dim_city AS city
    ON city.city_id = fact.city_id
ORDER BY fact.wind_speed_kmh DESC
LIMIT 5;

-- 4. Average wind speed on weekends compared with weekdays.
-- Business question: Are wind observations stronger on weekends or weekdays?
SELECT
    date.is_weekend,
    CASE date.is_weekend
        WHEN TRUE THEN 'Weekend'
        ELSE 'Weekday'
    END AS day_type,
    ROUND(AVG(fact.wind_speed_ms)::numeric, 2) AS avg_wind_speed_ms
FROM fact_weather_hourly AS fact
JOIN dim_date AS date
    ON date.date_id = fact.date_id
GROUP BY date.is_weekend
ORDER BY date.is_weekend;

-- 5. Average wind by city on weekends compared with weekdays.
-- Business question: Which cities have stronger average wind on each UK day type?
SELECT
    city.city_name,
    date.is_weekend,
    CASE date.is_weekend
        WHEN TRUE THEN 'Weekend'
        ELSE 'Weekday'
    END AS day_type,
    ROUND(AVG(fact.wind_speed_ms)::numeric, 2) AS avg_wind_speed_ms
FROM fact_weather_hourly AS fact
JOIN dim_city AS city
    ON city.city_id = fact.city_id
JOIN dim_date AS date
    ON date.date_id = fact.date_id
GROUP BY city.city_name, date.is_weekend
ORDER BY city.city_name, date.is_weekend;
