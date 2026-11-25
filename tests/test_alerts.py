import logging
from unittest.mock import MagicMock

import pytest

from weatherflow.alerts import check_risk_alerts
from weatherflow.config import ConfigurationError


def test_check_risk_alerts_logs_recent_high_risk_rows(monkeypatch, caplog):
    """Recent high-risk observations are logged without exposing credentials."""
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = [
        ("Cardiff", "open_meteo_forecast", "2026-11-25 09:00:00+00:00")
    ]
    monkeypatch.setattr("weatherflow.alerts.psycopg.connect", lambda url: connection)

    count = check_risk_alerts(
        config={"dq": {"timeliness_hours": 3}},
        database_url="postgresql://test",
    )

    assert count == 1
    assert "Risk alert: 1 recent high-risk" in caplog.text
    assert "Cardiff" in caplog.text
    connection.execute.assert_called_once()


def test_check_risk_alerts_reports_when_no_rows_are_high_risk(
    monkeypatch,
    caplog,
):
    """An empty risk query completes cleanly and is logged at info level."""
    caplog.set_level(logging.INFO)
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = []
    monkeypatch.setattr("weatherflow.alerts.psycopg.connect", lambda url: connection)

    assert check_risk_alerts(
        config={"dq": {"timeliness_hours": 3}},
        database_url="postgresql://test",
    ) == 0
    assert "No recent high-risk weather observations." in caplog.text


def test_check_risk_alerts_requires_database_url(monkeypatch):
    """Alert checks fail explicitly instead of pretending there are no risks."""
    monkeypatch.setattr("weatherflow.alerts.get_database_url", lambda: None)

    with pytest.raises(
        ConfigurationError,
        match="DATABASE_URL is required to check weather risk alerts",
    ):
        check_risk_alerts(config={"dq": {"timeliness_hours": 3}})
