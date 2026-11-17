from typing import Any

from .config import load_config
from .extract import extract
from .load import load
from .transform import transform


def run(config: dict[str, Any] | None = None) -> int:
    """Run extraction, transformation, and loading for the weather pipeline."""
    pipeline_config = config if config is not None else load_config()
    raw_data = extract(pipeline_config)
    transformed_data = transform(raw_data)
    return load(transformed_data, pipeline_config["paths"]["database"])
