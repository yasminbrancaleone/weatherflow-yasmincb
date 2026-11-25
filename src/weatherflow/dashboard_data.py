from pathlib import Path
import re
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row


def _read_rows(
    connection: psycopg.Connection[Any],
    query: str,
    params: tuple[Any, ...] = (),
) -> pd.DataFrame:
    return pd.DataFrame(connection.execute(query, params).fetchall())


def add_london_time(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Keep UTC timestamps and add their Europe/London display values."""
    result = dataframe.copy()
    if "observed_at_utc" in result and not result.empty:
        result["observed_at_utc"] = pd.to_datetime(
            result["observed_at_utc"],
            utc=True,
        )
        result["observed_at_london"] = result["observed_at_utc"].dt.tz_convert(
            "Europe/London"
        )
    return result


def flag_source_disagreements(
    comparisons: pd.DataFrame,
    threshold_c: float,
) -> pd.DataFrame:
    """Mark paired source readings that exceed the configured temperature delta."""
    result = add_london_time(comparisons)
    if result.empty:
        result["temperature_difference_c"] = pd.Series(dtype="float64")
        result["disagreement"] = pd.Series(dtype="bool")
        return result

    result["temperature_difference_c"] = (
        result["open_meteo_temperature_c"]
        - result["weatherapi_temperature_c"]
    ).abs()
    result["disagreement"] = (
        result["temperature_difference_c"] > threshold_c
    )
    return result


def load_latest_dq_summary(report_directory: Path) -> dict[str, int] | None:
    """Read counts from the newest generated Markdown DQ report."""
    reports = sorted(report_directory.glob("*.md"))
    if not reports:
        return None

    report = reports[-1].read_text(encoding="utf-8")
    good_rows = re.search(r"\*\*Good rows:\*\*\s*(\d+)", report)
    quarantined_rows = re.search(r"\*\*Quarantined rows:\*\*\s*(\d+)", report)
    passed_checks = len(re.findall(r"\|\s*PASS\s*\|", report))
    failed_checks = len(re.findall(r"\|\s*FAIL\s*\|", report))
    return {
        "good_rows": int(good_rows.group(1)) if good_rows else 0,
        "quarantined_rows": (
            int(quarantined_rows.group(1)) if quarantined_rows else 0
        ),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
    }


def load_dashboard_data(
    database_url: str,
    selected_city: str,
    disagreement_threshold_c: float,
    dq_report_directory: Path,
) -> dict[str, Any]:
    """Load risk, trend, source comparison, freshness, and DQ data."""
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        upcoming_risks = _read_rows(
            connection,
            """
            SELECT city.city_name, fact.observed_at_utc, fact.source,
                   fact.outdoor_work_risk, fact.category, fact.beaufort_scale,
                   fact.precipitation_mm, fact.wind_speed_kmh, fact.temperature_c
            FROM fact_weather_hourly AS fact
            JOIN dim_city AS city ON city.city_id = fact.city_id
            WHERE fact.observed_at_utc >= NOW()
              AND fact.observed_at_utc < NOW() + INTERVAL '24 hours'
            ORDER BY fact.observed_at_utc, city.city_name, fact.source
            """,
        )
        trends = _read_rows(
            connection,
            """
            SELECT city.city_name, fact.observed_at_utc,
                   AVG(fact.temperature_c) AS temperature_c,
                   AVG(fact.wind_speed_kmh) AS wind_speed_kmh
            FROM fact_weather_hourly AS fact
            JOIN dim_city AS city ON city.city_id = fact.city_id
            WHERE fact.observed_at_utc >= NOW() - INTERVAL '7 days'
              AND fact.observed_at_utc <= NOW()
            GROUP BY city.city_name, fact.observed_at_utc
            ORDER BY fact.observed_at_utc
            """,
        )
        source_comparison = _read_rows(
            connection,
            """
            SELECT fact.observed_at_utc,
                   MAX(fact.temperature_c) FILTER (
                       WHERE fact.source = 'open_meteo_forecast'
                   ) AS open_meteo_temperature_c,
                   MAX(fact.temperature_c) FILTER (
                       WHERE fact.source = 'weatherapi_forecast'
                   ) AS weatherapi_temperature_c
            FROM fact_weather_hourly AS fact
            JOIN dim_city AS city ON city.city_id = fact.city_id
            WHERE city.city_name = %s
              AND fact.source IN (
                  'open_meteo_forecast', 'weatherapi_forecast'
              )
              AND fact.observed_at_utc >= NOW()
              AND fact.observed_at_utc < NOW() + INTERVAL '24 hours'
            GROUP BY fact.observed_at_utc
            HAVING COUNT(DISTINCT fact.source) = 2
            ORDER BY fact.observed_at_utc
            """,
            (selected_city,),
        )
        latest_ingested = connection.execute(
            "SELECT MAX(ingested_at_utc) AS latest_ingested_at_utc "
            "FROM fact_weather_hourly"
        ).fetchone()

    return {
        "upcoming_risks": add_london_time(upcoming_risks),
        "trends": add_london_time(trends),
        "source_comparison": flag_source_disagreements(
            source_comparison,
            disagreement_threshold_c,
        ),
        "latest_ingested_at_utc": (
            latest_ingested["latest_ingested_at_utc"]
            if latest_ingested
            and latest_ingested["latest_ingested_at_utc"] is not None
            else None
        ),
        "dq_summary": load_latest_dq_summary(dq_report_directory),
    }
