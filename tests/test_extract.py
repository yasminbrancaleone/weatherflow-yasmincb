from pathlib import Path
import json
import logging
import pytest
import requests

from weatherflow.extract import _fetch_payload, extract, extract_weatherapi


class FakeResponse:
    """Minimal requests response used by extraction tests."""

    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload or {"hourly": {"time": ["2026-11-17T12:00"]}}
        self.ok = 200 <= status_code < 300

    def raise_for_status(self):
        """Raise an HTTP error for non-success status codes."""
        if not self.ok:
            raise requests.HTTPError(
                f"{self.status_code} response",
                response=self,
            )

    def json(self):
        """Return the fixture-like payload."""
        return self.payload


def test_fetch_retries_twice_then_succeeds(monkeypatch):
    """A server error retries twice and succeeds on the third request."""
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] <= 2:
            return FakeResponse(503)
        return FakeResponse(200)

    sleeps = []
    monkeypatch.setattr("weatherflow.extract.requests.get", fake_get)
    monkeypatch.setattr("weatherflow.extract.time.sleep", sleeps.append)
    city = {"name": "London", "latitude": 51.5, "longitude": -0.12}
    api_config = {
        "forecast_url": "https://example.test/forecast",
        "timeout_seconds": 10,
        "max_retries": 3,
        "past_days": 1,
        "forecast_days": 1,
        "hourly_variables": ["temperature_2m"],
        "timezone": "UTC",
    }

    payload = _fetch_payload(city, api_config)

    assert calls["count"] == 3
    assert sleeps == [1, 2]
    assert "hourly" in payload


def test_fetch_does_not_retry_not_found(monkeypatch):
    """A 404 response is raised without another API request."""
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return FakeResponse(404)

    monkeypatch.setattr("weatherflow.extract.requests.get", fake_get)
    monkeypatch.setattr(
        "weatherflow.extract.time.sleep",
        lambda seconds: pytest.fail("sleep should not be called"),
    )
    city = {"name": "London", "latitude": 51.5, "longitude": -0.12}
    api_config = {
        "forecast_url": "https://example.test/forecast",
        "timeout_seconds": 10,
        "max_retries": 3,
        "past_days": 1,
        "forecast_days": 1,
        "hourly_variables": ["temperature_2m"],
        "timezone": "UTC",
    }

    try:
        _fetch_payload(city, api_config)
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("404 response did not raise HTTPError")

    assert calls["count"] == 1


def test_fetch_retries_timeout(monkeypatch):
    """A timeout is retried with the configured backoff."""
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.Timeout("timed out")
        return FakeResponse(200)

    sleeps = []
    monkeypatch.setattr("weatherflow.extract.requests.get", fake_get)
    monkeypatch.setattr("weatherflow.extract.time.sleep", sleeps.append)
    city = {"name": "London", "latitude": 51.5, "longitude": -0.12}
    api_config = {
        "forecast_url": "https://example.test/forecast",
        "timeout_seconds": 10,
        "max_retries": 3,
        "past_days": 1,
        "forecast_days": 1,
        "hourly_variables": ["temperature_2m"],
        "timezone": "UTC",
    }

    payload = _fetch_payload(city, api_config)

    assert calls["count"] == 2
    assert sleeps == [1]
    assert "hourly" in payload


def test_extract_writes_raw_json_to_tmp_path(monkeypatch, tmp_path):
    """Extract writes each mock API payload beneath the configured raw path."""
    payload = {"hourly": {"time": ["2026-11-17T12:00"]}}
    monkeypatch.setattr(
        "weatherflow.extract.requests.get",
        lambda *args, **kwargs: FakeResponse(200, payload),
    )
    config = {
        "api": {
            "forecast_url": "https://example.test/forecast",
            "timeout_seconds": 10,
            "max_retries": 3,
            "past_days": 1,
            "forecast_days": 1,
            "hourly_variables": ["temperature_2m"],
            "timezone": "UTC",
        },
        "cities": [
            {"name": "London", "latitude": 51.5, "longitude": -0.12}
        ],
        "paths": {"raw_dir": tmp_path},
    }

    raw_payloads = extract(config)

    assert len(raw_payloads) == 1
    raw_files = list(tmp_path.rglob("*.json"))
    assert len(raw_files) == 1
    assert raw_files[0].is_file()


def test_extract_weatherapi_saves_original_payload_without_key(
    monkeypatch,
    tmp_path,
):
    """WeatherAPI requests use the key but raw payload files never contain it."""
    secret = "test-weatherapi-secret"
    payload = {
        "forecast": {
            "forecastday": [
                {"hour": [{"time_epoch": 1795478400, "temp_c": 8.1}]}
            ]
        }
    }
    request_arguments = {}

    def fake_get(url, params, timeout):
        request_arguments.update(url=url, params=params, timeout=timeout)
        return FakeResponse(200, payload)

    monkeypatch.setattr("weatherflow.extract.requests.get", fake_get)
    config = {
        "api": {
            "weatherapi_forecast_url": "https://example.test/forecast.json",
            "timeout_seconds": 10,
            "max_retries": 3,
            "forecast_days": 1,
        },
        "cities": [
            {"name": "London", "latitude": 51.5, "longitude": -0.12}
        ],
        "paths": {"raw_dir": tmp_path},
    }

    raw_payloads = extract_weatherapi(config, api_key=secret)

    assert request_arguments == {
        "url": "https://example.test/forecast.json",
        "params": {"key": secret, "q": "51.5,-0.12", "days": 1},
        "timeout": 10,
    }
    assert raw_payloads == [("London", payload)]
    raw_files = list(tmp_path.rglob("*.json"))
    assert len(raw_files) == 1
    assert json.loads(raw_files[0].read_text(encoding="utf-8")) == payload
    assert secret not in raw_files[0].read_text(encoding="utf-8")
    assert "weatherapi" in raw_files[0].name


def test_weatherapi_auth_failure_is_not_retried_or_logged_with_key(
    monkeypatch,
    caplog,
    tmp_path,
):
    """Authentication errors fail once with a sanitized message and logs."""
    secret = "test-weatherapi-secret"
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        logging.getLogger("urllib3.connectionpool").debug(
            "Request URL includes key=%s",
            secret,
        )
        response = FakeResponse(401)
        raise requests.HTTPError(
            f"401 https://example.test/forecast.json?key={secret}",
            response=response,
        )

    monkeypatch.setattr("weatherflow.extract.requests.get", fake_get)
    monkeypatch.setattr(
        "weatherflow.extract.time.sleep",
        lambda seconds: pytest.fail("Authentication failure must not retry."),
    )
    caplog.set_level(logging.DEBUG, logger="urllib3.connectionpool")
    config = {
        "api": {
            "weatherapi_forecast_url": "https://example.test/forecast.json",
            "timeout_seconds": 10,
            "max_retries": 3,
            "forecast_days": 1,
        },
        "cities": [
            {"name": "London", "latitude": 51.5, "longitude": -0.12}
        ],
        "paths": {"raw_dir": tmp_path},
    }

    with pytest.raises(requests.RequestException) as error:
        extract_weatherapi(config, api_key=secret)

    assert calls["count"] == 1
    assert "401" in str(error.value)
    assert secret not in str(error.value)
    assert secret not in caplog.text


def test_weatherapi_retries_server_errors_without_logging_key(
    monkeypatch,
    caplog,
    tmp_path,
):
    """WeatherAPI retries 5xx errors and keeps the key out of warning logs."""
    secret = "test-weatherapi-secret"
    calls = {"count": 0}
    delays = []

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return FakeResponse(503)
        return FakeResponse(200, {"forecast": {"forecastday": []}})

    monkeypatch.setattr("weatherflow.extract.requests.get", fake_get)
    monkeypatch.setattr("weatherflow.extract.time.sleep", delays.append)
    caplog.set_level(logging.WARNING)
    config = {
        "api": {
            "weatherapi_forecast_url": "https://example.test/forecast.json",
            "timeout_seconds": 10,
            "max_retries": 3,
            "forecast_days": 1,
        },
        "cities": [
            {"name": "London", "latitude": 51.5, "longitude": -0.12}
        ],
        "paths": {"raw_dir": tmp_path},
    }

    extract_weatherapi(config, api_key=secret)

    assert calls["count"] == 2
    assert delays == [1]
    assert secret not in caplog.text
    assert "HTTP status 503" in caplog.text
