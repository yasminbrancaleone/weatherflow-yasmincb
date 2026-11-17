import logging
from typing import Any

from .config import load_config
from .extract import extract
from .load import load, load_dimensions
from .output import write_processed_parquet, write_quarantine
from .reference import load_wmo_codes
from .transform import transform
from .validate import DataQualityError, validate


logger = logging.getLogger(__name__)


def run(config: dict[str, Any] | None = None) -> int:
    """Run extraction, transformation, and loading for the weather pipeline."""
    pipeline_config = config if config is not None else load_config()
    logger.info("Starting weather pipeline.")
    raw_data = extract(pipeline_config)
    transformed_data = transform(raw_data, load_wmo_codes())

    try:
        good_rows, quarantined_rows, check_results = validate(
            transformed_data,
            pipeline_config,
            run_mode="incremental",
        )
    except DataQualityError:
        logger.exception(
            "Blocking data quality failure prevented fact loading."
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
    rows_loaded = load(
        good_rows,
        pipeline_config["paths"]["database"],
        config=pipeline_config,
    )
    logger.info("Weather pipeline completed with %d loaded rows.", rows_loaded)
    return rows_loaded
