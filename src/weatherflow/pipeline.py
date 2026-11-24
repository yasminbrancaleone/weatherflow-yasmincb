import logging
from datetime import date
from typing import Any

from .config import load_config
from .extract import extract_archive, extract_incremental
from .load import load, load_dimensions, load_with_counts
from .output import (
    write_dq_report,
    write_processed_parquet,
    write_quarantine,
)
from .reference import load_wmo_codes
from .transform import transform
from .validate import CheckResult, DataQualityError, validate


logger = logging.getLogger(__name__)


def process_raw_records(
    raw_records: list[tuple[str, dict[str, Any]]],
    pipeline_config: dict[str, Any],
    source: str,
    run_mode: str = "incremental",
) -> int:
    """Transform, validate, and load raw records through one shared path."""
    if not raw_records:
        logger.warning("No raw records were provided for processing.")
        return 0

    transformed_data = transform(raw_records, load_wmo_codes())

    try:
        good_rows, quarantined_rows, check_results = validate(
            transformed_data,
            pipeline_config,
            run_mode=run_mode,
        )
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
            ],
            pipeline_config["paths"]["dq_report_dir"],
            good_rows=0,
            quarantined_rows=0,
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

    load_dimensions(pipeline_config, pipeline_config["paths"]["database"])
    processed_path = write_processed_parquet(
        good_rows, pipeline_config["paths"]["processed_dir"]
    )
    logger.info("Wrote processed Parquet output to %s.", processed_path)
    new_rows, updated_rows = load_with_counts(
        good_rows,
        pipeline_config["paths"]["database"],
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


def run(config: dict[str, Any] | None = None) -> int:
    """Run the incremental forecast pipeline."""
    pipeline_config = config if config is not None else load_config()
    logger.info("Starting incremental weather pipeline.")
    raw_data = extract_incremental(pipeline_config)
    return process_raw_records(
        raw_data,
        pipeline_config,
        source="open_meteo_forecast",
        run_mode="incremental",
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
