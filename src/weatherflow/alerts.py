import logging
from typing import Any

import psycopg

from .config import ConfigurationError, get_database_url, load_config


logger = logging.getLogger(__name__)


def check_risk_alerts(
    config: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> int:
    """Log high-risk observations within the configured timeliness window."""
    pipeline_config = config if config is not None else load_config()
    connection_url = database_url or get_database_url()
    if not connection_url:
        raise ConfigurationError(
            "DATABASE_URL is required to check weather risk alerts."
        )

    timeliness_hours = pipeline_config["dq"]["timeliness_hours"]
    with psycopg.connect(connection_url) as connection:
        rows = connection.execute(
            """
            SELECT city.city_name, fact.source, fact.observed_at_utc
            FROM fact_weather_hourly AS fact
            JOIN dim_city AS city ON city.city_id = fact.city_id
            WHERE fact.outdoor_work_risk = 'high'
              AND fact.observed_at_utc <= NOW()
              AND fact.observed_at_utc >= NOW() - (%s * INTERVAL '1 hour')
            ORDER BY fact.observed_at_utc DESC, city.city_name
            """,
            (timeliness_hours,),
        ).fetchall()

    if not rows:
        logger.info("No recent high-risk weather observations.")
        return 0

    logger.warning(
        "Risk alert: %d recent high-risk weather observations found.",
        len(rows),
    )
    for city_name, source, observed_at in rows:
        logger.warning(
            "High outdoor-work risk for %s from %s at %s.",
            city_name,
            source,
            observed_at,
        )
    return len(rows)
