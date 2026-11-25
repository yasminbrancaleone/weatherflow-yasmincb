from datetime import datetime, timedelta, timezone
import os
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import psycopg
import psycopg

from weatherflow.alerts import (
    build_risk_periods,
    check_risk_alerts,
    record_pipeline_failure_alert,
)
from weatherflow.config import ConfigurationError


TEST_DATABASE_URL = os.environ.get("DATABASE_URL")


def _mock_database(monkeypatch, execute_results):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.side_effect = execute_results
    monkeypatch.setattr("weatherflow.alerts.ensure_schema", MagicMock())
    monkeypatch.setattr(
        "weatherflow.alerts.psycopg.connect",
        MagicMock(return_value=connection),
    )
    return connection


def _rows():
    start = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    return [
        ("Cardiff", start, "rain", 3, 5.0),
        ("Cardiff", start, "storm", 7, 0.0),
        ("Cardiff", start + timedelta(hours=1), "snow", 2, 0.0),
    ]


def test_build_risk_periods_combines_sources_and_consecutive_hours():
    periods = build_risk_periods(_rows())

    assert len(periods) == 1
    assert periods[0].start_utc == datetime(
        2026, 11, 25, 12, tzinfo=timezone.utc
    )
    assert periods[0].end_utc == datetime(
        2026, 11, 25, 13, tzinfo=timezone.utc
    )
    assert periods[0].reasons == ("wind", "rain", "snow", "storm")
    assert periods[0].message == (
        "Cardiff: high outdoor-work risk due to wind, rain, snow, storm "
        "from 25 Nov 12:00 to 25 Nov 13:00 UK time."
    )


def test_check_risk_alerts_records_one_message_for_a_risk_period(
    monkeypatch,
    caplog,
):
    select_result = MagicMock()
    select_result.fetchall.return_value = _rows()
    inserted_result = MagicMock()
    inserted_result.fetchone.return_value = ("risk:Cardiff:2026-11-25T12:00:00+00:00",)
    connection = _mock_database(
        monkeypatch,
        [select_result, inserted_result, MagicMock()],
    )

    assert check_risk_alerts("postgresql://test") == 1

    query = connection.execute.call_args_list[0].args[0]
    assert "INTERVAL '12 hours'" in query
    assert "Cardiff: high outdoor-work risk" in caplog.text
    assert connection.execute.call_count == 3


def test_check_risk_alerts_suppresses_duplicate_alerts(monkeypatch):
    select_result = MagicMock()
    select_result.fetchall.return_value = _rows()
    inserted_result = MagicMock()
    inserted_result.fetchone.return_value = ("risk:Cardiff:2026-11-25T12:00:00+00:00",)
    duplicate_result = MagicMock()
    duplicate_result.fetchone.return_value = None
    connection = _mock_database(
        monkeypatch,
        [
            select_result,
            inserted_result,
            MagicMock(),
            select_result,
            duplicate_result,
        ],
    )

    assert check_risk_alerts("postgresql://test") == 1
    assert check_risk_alerts("postgresql://test") == 0
    assert connection.execute.call_count == 5


def test_pipeline_failure_alert_records_dag_task_and_try_without_url(
    monkeypatch,
    caplog,
):
    inserted_result = MagicMock()
    inserted_result.fetchone.return_value = ("pipeline-failure-key",)
    connection = _mock_database(
        monkeypatch,
        [inserted_result, MagicMock()],
    )

    assert record_pipeline_failure_alert(
        dag_id="weatherflow_hourly",
        task_id="run_weatherapi",
        run_id="scheduled__2026-11-25T12:00:00+00:00",
        try_number=3,
        database_url="postgresql://test-credential",
    )

    message = connection.execute.call_args_list[1].args[1][2]
    assert "DAG weatherflow_hourly" in message
    assert "task run_weatherapi" in message
    assert "try 3" in message
    assert "test-credential" not in caplog.text


def test_alerts_require_database_url(monkeypatch):
    monkeypatch.setattr("weatherflow.alerts.get_database_url", lambda: None)

    with pytest.raises(
        ConfigurationError,
        match="DATABASE_URL is required to record weather alerts",
    ):
        check_risk_alerts()


def test_pipeline_failure_is_logged_when_warehouse_is_unavailable(
    monkeypatch,
    caplog,
):
    def fail_schema(url):
        assert url == "postgresql://test-credential"
        raise psycopg.OperationalError("offline")

    monkeypatch.setattr(
        "weatherflow.alerts.ensure_schema",
        fail_schema,
    )

    with pytest.raises(psycopg.OperationalError, match="offline"):
        record_pipeline_failure_alert(
            dag_id="weatherflow_hourly",
            task_id="run_open_meteo",
            run_id="scheduled-run",
            try_number=3,
            database_url="postgresql://test-credential",
        )

    assert "Pipeline failure alert could not be persisted" in caplog.text
    assert "test-credential" not in caplog.text


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set DATABASE_URL to run PostgreSQL alert integration tests.",
)
def test_postgres_pipeline_alert_is_idempotent():
    assert TEST_DATABASE_URL is not None
    run_id = f"test-{uuid4()}"
    alert_key = f"pipeline_failure:test_dag:test_task:{run_id}"
    try:
        assert record_pipeline_failure_alert(
            dag_id="test_dag",
            task_id="test_task",
            run_id=run_id,
            try_number=3,
            database_url=TEST_DATABASE_URL,
        )
        assert not record_pipeline_failure_alert(
            dag_id="test_dag",
            task_id="test_task",
            run_id=run_id,
            try_number=3,
            database_url=TEST_DATABASE_URL,
        )
        with psycopg.connect(TEST_DATABASE_URL) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM alerts WHERE alert_key = %s",
                (alert_key,),
            ).fetchone()
        assert row == (1,)
    finally:
        with psycopg.connect(TEST_DATABASE_URL) as connection:
            connection.execute(
                "DELETE FROM alerts WHERE alert_key = %s",
                (alert_key,),
            )
            connection.execute(
                "DELETE FROM alerts_sent WHERE alert_key = %s",
                (alert_key,),
            )
