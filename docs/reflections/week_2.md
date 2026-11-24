# Week 2 Reflection

## What I built

I refactored the Week 1 script into an installable and configurable weather pipeline.
The project now separates extraction, transformation, loading, validation, and
command-line orchestration. I added a dimensional SQLite model, WMO descriptions,
derived business metrics, partitioned Parquet output, data quality quarantine,
automated tests, historical backfill, and incremental high-water-mark loading.

## Data engineering lessons

- Pure functions make transformations easier to test and reuse.
- UTC timestamps avoid ambiguous local-time conversions; Europe/London is derived
  only for display and the local business date.
- A star schema separates descriptive dimensions from measured fact records.
- Composite keys and upserts make repeated loads deterministic.
- Transactions prevent partial fact loads when a database constraint fails.
- Quarantine keeps invalid records available for investigation instead of silently
  discarding them.
- Incremental windows need a two-hour overlap, while the watermark must ignore
  forecast rows that occur after the current UTC time.
- Historical API extraction should be chunked and separated from the
  forecast extraction path.

## Challenges and resolutions

Migrating the wide table to a star schema required resolving city and date
surrogate keys and preserving idempotency. I used foreign keys, dimension upserts,
and a composite fact-key upsert. Data quality checks initially exposed type and
null-handling bugs, especially for incomplete temperature readings. Numeric
conversion now happens before consistency calculations.

The testing work also found a Beaufort boundary issue. I normalized the wind
speed before the band calculation so a value at exactly `13.9 m/s` maps
deterministically to Beaufort 7.

## Skills tracker

| Skill | Progress |
|---|---|
| Python packaging and CLI entry points | Confident |
| YAML configuration | Confident |
| Logging and retries | Confident |
| Pure transformation functions | Confident |
| Parquet output | Confident |
| Star schema modelling | Confident |
| SQLite upserts and transactions | Confident |
| Data quality checks and quarantine | Confident |
| pytest fixtures and mocking | Confident |
| Code coverage | Confident |
| Backfill chunking | Confident |
| Incremental watermarks | Confident |
| Pull request and code review workflow | In progress |

## D2.6 validation evidence

I ran the 30-day backfill for 2026-10-21 through 2026-11-19 twice:

- First run: 840 new rows and 2,760 updated rows (3,600 observations processed).
- Second run: 0 new rows and 3,600 updated rows (3,600 observations processed).

The database contained 4,800 fact rows after the two runs. The second run confirms
idempotent loading and a stable 3,600-row backfill result.
