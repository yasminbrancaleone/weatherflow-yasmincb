import logging
from typing import Any

from .config import load_config
from .extract import extract
from .load import load
from .reference import load_wmo_codes
from .transform import transform


logger = logging.getLogger(__name__)


def run(config: dict[str, Any] | None = None) -> int:
    """Run extraction, transformation, and loading for the weather pipeline."""
    pipeline_config = config if config is not None else load_config()
    logger.info("Starting weather pipeline.")
    raw_data = extract(pipeline_config)
    transformed_data = transform(raw_data, load_wmo_codes())
    rows_loaded = load(transformed_data, pipeline_config["paths"]["database"])
    logger.info("Weather pipeline completed with %d loaded rows.", rows_loaded)
    return rows_loaded
