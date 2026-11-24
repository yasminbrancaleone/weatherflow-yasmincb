"""Tests for backfill CLI and shared pipeline routing."""

from datetime import date
from unittest.mock import patch

import weatherflow.__main__ as cli
import weatherflow.pipeline as pipeline
import pytest
from weatherflow.config import ConfigurationError


def test_backfill_parser_accepts_explicit_dates():
    """The CLI parser reads start and end dates."""
    arguments = cli.create_parser().parse_args(
        [
            "backfill",
            "--start-date",
            "2026-10-01",
            "--end-date",
            "2026-10-10",
        ]
    )

    assert arguments.command == "backfill"
    assert arguments.start_date == date(2026, 10, 1)
    assert arguments.end_date == date(2026, 10, 10)


def test_resolve_backfill_dates_rejects_inverted_range():
    """An inverted backfill date range is rejected."""
    arguments = cli.create_parser().parse_args(
        [
            "backfill",
            "--start-date",
            "2026-10-10",
            "--end-date",
            "2026-10-01",
        ]
    )

    try:
        cli.resolve_backfill_dates(arguments)
    except ValueError:
        pass
    else:
        raise AssertionError("Inverted range was accepted")


def test_main_dispatches_forecast_run(monkeypatch):
    """The run subcommand dispatches the forecast pipeline."""
    selected_sources = []
    monkeypatch.setattr(
        "weatherflow.__main__.run_pipeline",
        lambda source: selected_sources.append(source),
    )

    assert cli.main(["run"]) == 0
    assert selected_sources == ["all"]


def test_run_parser_accepts_source_selection():
    """The run command accepts each supported weather-source selector."""
    for source in ("open_meteo", "weatherapi", "all"):
        arguments = cli.create_parser().parse_args(["run", "--source", source])
        assert arguments.source == source


def test_main_dispatches_backfill(monkeypatch):
    """The backfill subcommand dispatches run_backfill."""
    monkeypatch.setattr(
        "weatherflow.__main__.run_backfill",
        lambda start, end: 7,
    )
    arguments = ["backfill", "--start-date", "2026-10-01", "--end-date", "2026-10-10"]

    assert cli.main(arguments) == 0


def test_incremental_run_uses_forecast_source():
    """The incremental run routes raw data through the forecast source."""
    raw_records = [("London", {"hourly": {"time": []}})]
    config = {"paths": {}}

    with patch.object(pipeline, "extract_incremental", return_value=raw_records), patch.object(
        pipeline,
        "process_raw_records",
        return_value=3,
    ) as process:
        assert pipeline.run(config, source="open_meteo") == 3

    process.assert_called_once_with(
        raw_records,
        config,
        source="open_meteo_forecast",
        run_mode="incremental",
    )


def test_all_sources_fail_before_any_request_when_weatherapi_key_is_missing():
    """The key is checked before extraction from either source begins."""
    config = {"paths": {}}
    with patch.object(
        pipeline,
        "load_weatherapi_key",
        side_effect=ConfigurationError("WEATHERAPI_KEY is required."),
    ), patch.object(
        pipeline,
        "extract_incremental",
        side_effect=AssertionError("Open-Meteo request should not be made."),
    ) as open_meteo_extract, pytest.raises(
        ConfigurationError,
        match="WEATHERAPI_KEY is required",
    ):
        pipeline.run(config, source="all")

    open_meteo_extract.assert_not_called()


def test_all_sources_use_the_shared_processing_path():
    """Both providers route through the same transform/validate/load function."""
    config = {"paths": {}}
    open_meteo_records = [("London", {"hourly": {"time": []}})]
    weatherapi_records = [("London", {"forecast": {"forecastday": []}})]

    with patch.object(
        pipeline,
        "load_weatherapi_key",
        return_value="test-key",
    ), patch.object(
        pipeline,
        "extract_incremental",
        return_value=open_meteo_records,
    ), patch.object(
        pipeline,
        "extract_weatherapi",
        return_value=weatherapi_records,
    ), patch.object(
        pipeline,
        "process_raw_records",
        side_effect=[2, 3],
    ) as process:
        assert pipeline.run(config, source="all") == 5

    assert process.call_args_list[0].args == (open_meteo_records, config)
    assert process.call_args_list[0].kwargs == {
        "source": "open_meteo_forecast",
        "run_mode": "incremental",
    }
    assert process.call_args_list[1].args == (weatherapi_records, config)
    assert process.call_args_list[1].kwargs == {
        "source": "weatherapi_forecast",
        "run_mode": "incremental",
    }


def test_backfill_run_uses_archive_source():
    """The backfill route uses archive extraction and full validation."""
    raw_records = [("London", {"hourly": {"time": []}})]
    config = {"paths": {}}

    with patch.object(
        pipeline,
        "extract_archive",
        return_value=raw_records,
    ), patch.object(
        pipeline,
        "process_raw_records",
        return_value=30,
    ) as process:
        assert pipeline.run_backfill(
            date(2026, 10, 14),
            date(2026, 11, 12),
            config,
        ) == 30

    process.assert_called_once_with(
        raw_records,
        config,
        source="open_meteo_archive",
        run_mode="full",
    )


def test_process_raw_records_returns_zero_without_data():
    """An empty extraction result is not sent to transformation or loading."""
    assert pipeline.process_raw_records(
        [],
        {"paths": {}},
        source="open_meteo_forecast",
    ) == 0
