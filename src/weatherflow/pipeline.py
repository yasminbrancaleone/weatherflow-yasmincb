import logging
from datetime import date
from typing import Any

from .config import get_database_url, load_config, load_weatherapi_key
from .extract import extract_archive, extract_incremental, extract_weatherapi
from .load import load, load_dimensions, load_with_counts
from .output import (
    write_dq_report,
    write_processed_parquet,
    write_quarantine,
)
from .postgres import load_with_counts as load_postgres_with_counts
from .reference import load_weatherapi_codes, load_wmo_codes
from .transform import normalise_records, transform
from .validate import (
    CheckResult,
    DataQualityError,
    compare_source_temperatures,
    validate,
)


logger = logging.getLogger(__name__)


def process_raw_records(
    raw_records: list[tuple[str, dict[str, Any]]],
    pipeline_config: dict[str, Any],
    source: str,
    run_mode: str = "incremental",
    additional_checks: tuple[CheckResult, ...] = (),
) -> int:
    """Transform, validate, and load raw records through one shared path."""
    if not raw_records:
        logger.warning("No raw records were provided for processing.")
        return 0

    weather_codes = (
        load_weatherapi_codes()
        if source == "weatherapi_forecast"
        else load_wmo_codes()
    )
    transformed_data = transform(
        raw_records,
        weather_codes,
        source=source,
    )

    try:
        good_rows, quarantined_rows, check_results = validate(
            transformed_data,
            pipeline_config,
            run_mode=run_mode,
        )
        check_results.extend(additional_checks)
    except DataQualityError as error:
        logger.exception(
            "Blocking data quality failure prevented fact loading."
        )
        write_dq_report(
            [
                CheckResult(
                    name="blocking_data_quality_failure",
                    dimension="validation",
                    severity="fail",
                    passed=False,
                    failed_rows=1,
                    details=str(error),
                )
            ]
            + list(additional_checks),
            pipeline_config["paths"]["dq_report_dir"],
            good_rows=0,
            quarantined_rows=0,
            suffix=source,
        )
        raise

    quarantine_path = write_quarantine(
        quarantined_rows,
        pipeline_config["paths"]["quarantine_dir"],
    )
    if quarantine_path is not None:
        logger.warning(
            "Quarantined %d rows; excluded them from loading.",
            len(quarantined_rows),
        )

    write_dq_report(
        check_results,
        pipeline_config["paths"]["dq_report_dir"],
        good_rows=len(good_rows),
        quarantined_rows=len(quarantined_rows),
        suffix=source,
    )

    warned_checks = [result for result in check_results if result.severity == "warn" and not result.passed]
    for result in warned_checks:
        logger.warning(
            "Data quality warning %s: %s",
            result.name,
            result.details,
        )

    if good_rows.empty:
        logger.warning("No good rows remain after data quality validation.")
        return 0

    database_url = get_database_url()
    if database_url is None:
        logger.info(
            "Using SQLite database at %s.",
            pipeline_config["paths"]["database"],
        )
        load_dimensions(
            pipeline_config,
            pipeline_config["paths"]["database"],
        )
    else:
        logger.info("Using the PostgreSQL warehouse from DATABASE_URL.")
    processed_path = write_processed_parquet(
        good_rows,
        pipeline_config["paths"]["processed_dir"],
        suffix=source,
    )
    logger.info("Wrote processed Parquet output to %s.", processed_path)
    if database_url is None:
        new_rows, updated_rows = load_with_counts(
            good_rows,
            pipeline_config["paths"]["database"],
            config=pipeline_config,
            source=source,
        )
    else:
        new_rows, updated_rows = load_postgres_with_counts(
            good_rows,
            database_url,
            config=pipeline_config,
            source=source,
        )
    processed_rows = new_rows + updated_rows
    logger.info(
        "Weather pipeline completed: %d new rows, %d updated rows.",
        new_rows,
        updated_rows,
    )
    return processed_rows


def run(
    config: dict[str, Any] | None = None,
    source: str = "all",
) -> int:
    """Run incremental extraction from the selected weather source(s)."""
    supported_sources = {"open_meteo", "weatherapi", "all"}
    if source not in supported_sources:
        raise ValueError(
            "source must be one of: open_meteo, weatherapi, all."
        )

    pipeline_config = config if config is not None else load_config()
    api_key = (
        load_weatherapi_key()
        if source in {"weatherapi", "all"}
        else None
    )
    source_runs: list[tuple[list[tuple[str, dict[str, Any]]], str]] = []
    if source in {"open_meteo", "all"}:
        logger.info("Starting incremental Open-Meteo pipeline.")
        source_runs.append(
            (extract_incremental(pipeline_config), "open_meteo_forecast")
        )
    if source in {"weatherapi", "all"}:
        logger.info("Starting incremental WeatherAPI pipeline.")
        source_runs.append(
            (
                extract_weatherapi(pipeline_config, api_key=api_key),
                "weatherapi_forecast",
            )
        )

    cross_source_check = None
    cross_source_report_source = None
    if source == "all":
        open_meteo_records = source_runs[0][0]
        weatherapi_records = source_runs[1][0]
        cross_source_report_source = next(
            (
                source_name
                for raw_data, source_name in source_runs
                if raw_data
            ),
            None,
        )
        cross_source_check = compare_source_temperatures(
            normalise_records(open_meteo_records, "open_meteo_forecast"),
            normalise_records(weatherapi_records, "weatherapi_forecast"),
            pipeline_config["dq"]["cross_source_temperature_tolerance_c"],
        )

    return sum(
        process_raw_records(
            raw_data,
            pipeline_config,
            source=source_name,
            run_mode="incremental",
            additional_checks=(cross_source_check,)
            if cross_source_check is not None
            and source_name == cross_source_report_source
            else (),
        )
        for raw_data, source_name in source_runs
    )


def run_backfill(
    start_date: date,
    end_date: date,
    config: dict[str, Any] | None = None,
) -> int:
    """Run a historical backfill through the shared pipeline path."""
    pipeline_config = config if config is not None else load_config()
    logger.info(
        "Starting archive backfill from %s through %s.",
        start_date.isoformat(),
        end_date.isoformat(),
    )
    raw_records = extract_archive(
        pipeline_config,
        start_date,
        end_date,
    )
    return process_raw_records(
        raw_records,
        pipeline_config,
        source="open_meteo_archive",
        run_mode="full",
    )
