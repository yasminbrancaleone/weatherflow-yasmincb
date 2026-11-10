# Week 1 Reflection

## What I built

I built a small end-to-end ETL pipeline that requests hourly forecasts for five UK cities, preserves each API response as raw JSON, transforms the hourly records with pandas, and loads them into SQLite. The raw landing area keeps the source payloads separate from the queryable `weather_hourly` table.

## What I learned

- The raw payload and the analytical table serve different purposes: raw files preserve what the API returned, while the transformed table has a documented schema and a clear city-and-hour grain.
- Timestamps need a consistent representation as well as a datetime type. Equivalent strings such as `2026-11-09T00:00` and `2026-11-09T00:00:00` can otherwise become different SQLite keys.
- A composite key and an upsert make reruns safer, but the values used to construct that key must be normalized consistently.
- Exploring the dataset before writing SQL helped identify repeated observations and the difference between location-level attributes in the raw data and fields retained in the final table.
- Keeping the database and raw extracts out of Git avoids committing generated data while retaining the code and documentation needed to reproduce the pipeline.

## Challenge and resolution

The main data-quality issue was timestamp formatting. The database already contained rows for the same city and hour with different timestamp strings, so the primary key alone did not prevent logical duplicates. I updated the load step to serialize timestamps canonically and merge existing rows that resolve to the same city and second, keeping the most recently ingested row.

I also aligned the data dictionary with the actual SQLite table instead of describing the raw API payload as if all those fields were loaded.

## Next steps

I would add automated tests for timestamp normalization and idempotent loading, then improve failure handling so an unsuccessful city extraction is more visible to the person running the pipeline. I would also continue checking the observation timezone and API units whenever the pipeline's output schema changes.
