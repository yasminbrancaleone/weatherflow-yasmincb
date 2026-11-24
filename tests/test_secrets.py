import pytest

from weatherflow.config import ConfigurationError, load_weatherapi_key


def test_load_weatherapi_key_reads_project_env_file(monkeypatch, tmp_path):
    """The WeatherAPI key is loaded from the project .env file."""
    monkeypatch.delenv("WEATHERAPI_KEY", raising=False)
    monkeypatch.setattr(
        "weatherflow.config.CONFIG_FILE",
        tmp_path / "config.yaml",
    )
    (tmp_path / ".env").write_text(
        "WEATHERAPI_KEY=test-weatherapi-key\n",
        encoding="utf-8",
    )

    assert load_weatherapi_key() == "test-weatherapi-key"


def test_load_weatherapi_key_fails_when_missing(monkeypatch, tmp_path):
    """A missing key produces a clear error without exposing a key value."""
    monkeypatch.delenv("WEATHERAPI_KEY", raising=False)
    monkeypatch.setattr(
        "weatherflow.config.CONFIG_FILE",
        tmp_path / "config.yaml",
    )

    with pytest.raises(ConfigurationError, match="WEATHERAPI_KEY is required"):
        load_weatherapi_key()
