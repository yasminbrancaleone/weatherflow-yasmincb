-- Query 1: Total record count, minimum, and maximum observation time per city
-- Business Question: What is the time coverage and total volume of data available per city?
SELECT 
    city,
    COUNT(*) AS total_records,
    MIN(observed_at) AS earliest_observation,
    MAX(observed_at) AS latest_observation
FROM weather_hourly
GROUP BY city
ORDER BY city;

-- Query 2: Average temperature per city for yesterday
-- Business Question: What was the average temperature profile across each city for yesterday?
SELECT 
    city,
    ROUND(AVG(temperature_c), 2) AS avg_temperature_c
FROM weather_hourly
WHERE DATE(observed_at) = DATE('now', '-1 day', 'localtime')
GROUP BY city
ORDER BY avg_temperature_c DESC;

-- Query 3: Top 5 windiest hours across all cities
-- Business Question: What were the highest wind speeds recorded, and where/when did they occur?
SELECT 
    city,
    observed_at,
    wind_speed_kmh,
    weather_code
FROM weather_hourly
ORDER BY wind_speed_kmh DESC
LIMIT 5;