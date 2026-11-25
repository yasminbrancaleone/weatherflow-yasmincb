from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Iterable
from zoneinfo import ZoneInfo

import psycopg

from .config import ConfigurationError, get_database_url
from .postgres import ensure_schema


logger = logging.getLogger(__name__)
_LONDON = ZoneInfo("Europe/London")


@dataclass(frozen=True)
class RiskPeriod:
    city_name: str
    start_utc: datetime
    end_utc: datetime
    reasons: tuple[str, ...]

    @property
    def alert_key(self) -> str:
        return f"risk:{self.city_name}:{self.start_utc.isoformat()}"

    @property
    def message(self) -> str:
        start_london = self.start_utc.astimezone(_LONDON)
        end_london = self.end_utc.astimezone(_LONDON)
        reasons = ", ".join(self.reasons)
        return (
            f"{self.city_name}: high outdoor-work risk due to {reasons} "
            f"from {start_london:%d %b %H:%M} to "
            f"{end_london:%d %b %H:%M} UK time."
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reasons_for_row(
    category: str | None,
    beaufort_scale: int | None,
    precipitation_mm: float | None,
) -> set[str]:
    reasons = set()
    if beaufort_scale is not None and beaufort_scale >= 7:
        reasons.add("wind")
    if precipitation_mm is not None and precipitation_mm >= 4:
        reasons.add("rain")
    if category == "snow":
        reasons.add("snow")
    if category == "storm":
        reasons.add("storm")
    return reasons


def build_risk_periods(
    rows: Iterable[tuple[str, datetime, str | None, int | None, float | None]],
) -> list[RiskPeriod]:
    """Combine duplicate source readings into contiguous city risk periods."""
    city_hours: dict[str, dict[datetime, set[str]]] = {}
    for city_name, observed_at, category, beaufort, precipitation in rows:
        timestamp = _as_utc(observed_at)
        reasons = _reasons_for_row(category, beaufort, precipitation)
        city_hours.setdefault(city_name, {}).setdefault(timestamp, set()).update(
            reasons
        )

    periods = []
    reason_order = ("wind", "rain", "snow", "storm")
    for city_name, hourly_risks in sorted(city_hours.items()):
        timestamps = sorted(hourly_risks)
        start = previous = timestamps[0]
        period_reasons = set(hourly_risks[start])

        def append_period(period_start: datetime, period_end: datetime) -> None:
            ordered_reasons = tuple(
                reason for reason in reason_order if reason in period_reasons
            )
            periods.append(
                RiskPeriod(
                    city_name=city_name,
                    start_utc=period_start,
                    end_utc=period_end,
                    reasons=ordered_reasons or ("high-risk conditions",),
                )
            )

        for timestamp in timestamps[1:]:
            if timestamp != previous + timedelta(hours=1):
                append_period(start, previous)
                start = timestamp
                period_reasons = set()
            period_reasons.update(hourly_risks[timestamp])
            previous = timestamp
        append_period(start, previous)

    return periods


def _resolve_database_url(database_url: str | None) -> str:
    connection_url = database_url or get_database_url()
    if not connection_url:
        raise ConfigurationError(
            "DATABASE_URL is required to record weather alerts."
        )
    return connection_url


def _persist_alert(
    database_url: str,
    alert_key: str,
    alert_type: str,
    message: str,
    *,
    city_name: str | None = None,
    period_start_utc: datetime | None = None,
    period_end_utc: datetime | None = None,
    dag_id: str | None = None,
    task_id: str | None = None,
    try_number: int | None = None,
) -> bool:
    with psycopg.connect(database_url) as connection:
        inserted = connection.execute(
            """
            INSERT INTO alerts_sent (alert_key)
            VALUES (%s)
            ON CONFLICT (alert_key) DO NOTHING
            RETURNING alert_key
            """,
            (alert_key,),
        ).fetchone()
        if inserted is None:
            return False

        connection.execute(
            """
            INSERT INTO alerts (
                alert_key, alert_type, message, city_name,
                period_start_utc, period_end_utc, dag_id, task_id, try_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                alert_key,
                alert_type,
                message,
                city_name,
                period_start_utc,
                period_end_utc,
                dag_id,
                task_id,
                try_number,
            ),
        )

    logger.warning("Alert recorded: %s", message)
    return True


def check_risk_alerts(database_url: str | None = None) -> int:
    """Record one deduplicated alert for each high-risk period in 12 hours."""
    connection_url = _resolve_database_url(database_url)
    ensure_schema(connection_url)

    with psycopg.connect(connection_url) as connection:
        rows = connection.execute(
            """
            SELECT city.city_name, fact.observed_at_utc, fact.category,
                   fact.beaufort_scale, fact.precipitation_mm
            FROM fact_weather_hourly AS fact
            JOIN dim_city AS city ON city.city_id = fact.city_id
            WHERE fact.outdoor_work_risk = 'high'
              AND fact.observed_at_utc >= NOW()
              AND fact.observed_at_utc < NOW() + INTERVAL '12 hours'
            ORDER BY city.city_name, fact.observed_at_utc
            """
        ).fetchall()

    if not rows:
        logger.info("No high-risk weather periods in the next 12 hours.")
        return 0

    sent_count = sum(
        _persist_alert(
            connection_url,
            period.alert_key,
            "risk",
            period.message,
            city_name=period.city_name,
            period_start_utc=period.start_utc,
            period_end_utc=period.end_utc,
        )
        for period in build_risk_periods(rows)
    )
    logger.info(
        "Recorded %d new risk alert(s); duplicate alerts were suppressed.",
        sent_count,
    )
    return sent_count


def record_pipeline_failure_alert(
    dag_id: str,
    task_id: str,
    run_id: str,
    try_number: int,
    database_url: str | None = None,
) -> bool:
    """Persist and log one deduplicated alert for a failed Airflow task run."""
    message = (
        f"Pipeline failure: DAG {dag_id}, task {task_id}, "
        f"try {try_number} (run {run_id})."
    )
    try:
        connection_url = _resolve_database_url(database_url)
        ensure_schema(connection_url)
        return _persist_alert(
            connection_url,
            f"pipeline_failure:{dag_id}:{task_id}:{run_id}",
            "pipeline_failure",
            message,
            dag_id=dag_id,
            task_id=task_id,
            try_number=try_number,
        )
    except (ConfigurationError, OSError, psycopg.Error):
        logger.error("Pipeline failure alert could not be persisted: %s", message)
        raise
