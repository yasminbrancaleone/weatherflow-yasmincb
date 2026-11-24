import pytest

from weatherflow.config import (
    ConfigurationError,
    get_database_url,
)


def test_get_database_url_loads_value_from_project_env(monkeypatch, tmp_path):
    """The Postgres connection URL can be loaded from the project .env file."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        "weatherflow.config.CONFIG_FILE",
        tmp_path / "config.yaml",
    )
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://weatherflow:test-password@localhost:5433/weatherflow\n",
        encoding="utf-8",
    )

    assert (
        get_database_url()
        == "postgresql://weatherflow:test-password@localhost:5433/weatherflow"
    )


def test_get_database_url_rejects_non_postgresql_schemes(monkeypatch, tmp_path):
    """The connection URL cannot silently select an unsupported backend."""
    monkeypatch.setattr(
        "weatherflow.config.CONFIG_FILE",
        tmp_path / "config.yaml",
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite:///weather.db")

    with pytest.raises(
        ConfigurationError,
        match="DATABASE_URL must use the postgresql:// or postgres:// scheme",
    ):
        get_database_url()
