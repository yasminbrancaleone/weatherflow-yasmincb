"""Tests for backfill CLI and shared pipeline routing."""

from datetime import date
from unittest.mock import patch

import weatherflow.__main__ as cli
import weatherflow.pipeline as pipeline


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
    monkeypatch.setattr(
        "weatherflow.__main__.run_pipeline",
        lambda: 7,
    )

    assert cli.main(["run"]) == 0


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
        assert pipeline.run(config) == 3

    process.assert_called_once_with(
        raw_records,
        config,
        source="open_meteo_forecast",
        run_mode="incremental",
    )


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
