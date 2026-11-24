"""Integration tests for the PostgreSQL warehouse."""

from datetime import timedelta
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from weatherflow.config import load_config
from weatherflow.load import _canonical_utc
from weatherflow.postgres import get_high_water_mark, load_with_counts
from weatherflow.reference import load_wmo_codes
from weatherflow.transform import transform


TEST_DATABASE_URL = os.environ.get("WEATHERFLOW_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set WEATHERFLOW_TEST_DATABASE_URL to run PostgreSQL integration tests.",
)


def _delete_test_source(source: str) -> None:
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        connection.execute(
            "DELETE FROM fact_weather_hourly WHERE source = %s",
            (source,),
        )


def _count_test_source(source: str) -> int:
    with psycopg.connect(TEST_DATABASE_URL) as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM fact_weather_hourly WHERE source = %s",
            (source,),
        ).fetchone()[0]


def test_postgres_load_is_idempotent_and_reports_high_water_mark(london_payload):
    """Three upserts keep one row per key and track new versus updated facts."""
    source = f"postgres_test_{uuid4().hex}"
    config = load_config()
    transformed = transform(
        [("London", london_payload)],
        load_wmo_codes(),
    )

    try:
        assert load_with_counts(
            transformed,
            TEST_DATABASE_URL,
            config,
            source,
        ) == (6, 0)
        assert load_with_counts(
            transformed,
            TEST_DATABASE_URL,
            config,
            source,
        ) == (0, 6)
        assert load_with_counts(
            transformed,
            TEST_DATABASE_URL,
            config,
            source,
        ) == (0, 6)
        assert _count_test_source(source) == 6

        latest_observation = transformed["observed_at_utc"].max()
        mark = get_high_water_mark(
            TEST_DATABASE_URL,
            "London",
            source,
            now_utc=latest_observation.to_pydatetime() + timedelta(seconds=1),
        )
        assert mark is not None
        assert _canonical_utc(mark) == _canonical_utc(latest_observation)
    finally:
        _delete_test_source(source)


def test_postgres_load_rolls_back_all_facts_on_constraint_failure(london_payload):
    """A fact constraint failure rolls back every fact from that load."""
    source = f"postgres_rollback_test_{uuid4().hex}"
    config = load_config()
    transformed = transform(
        [("London", london_payload)],
        load_wmo_codes(),
    ).iloc[:2].copy()
    transformed.iloc[1, transformed.columns.get_loc("outdoor_work_risk")] = (
        "invalid-risk"
    )

    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            load_with_counts(
                transformed,
                TEST_DATABASE_URL,
                config,
                source,
            )
        assert _count_test_source(source) == 0
    finally:
        _delete_test_source(source)


def test_analysis_queries_run_on_postgres(london_payload):
    """All documented analysis queries execute against the PostgreSQL schema."""
    source = f"postgres_analysis_test_{uuid4().hex}"
    config = load_config()
    transformed = transform(
        [("London", london_payload)],
        load_wmo_codes(),
    )
    queries_path = Path(__file__).parents[1] / "sql" / "analysis_queries.sql"
    queries = [
        query.strip()
        for query in queries_path.read_text(encoding="utf-8").split(";")
        if query.strip()
    ]

    try:
        load_with_counts(transformed, TEST_DATABASE_URL, config, source)
        assert len(queries) == 5
        with psycopg.connect(TEST_DATABASE_URL) as connection:
            for query in queries:
                connection.execute(query).fetchall()
    finally:
        _delete_test_source(source)
