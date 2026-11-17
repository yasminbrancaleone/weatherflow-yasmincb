from datetime import datetime, timezone
import logging
from pathlib import Path

import pandas as pd


logger = logging.getLogger(__name__)


def write_processed_parquet(
    dataframe: pd.DataFrame,
    processed_dir: Path | str,
    run_at: datetime | None = None,
) -> Path:
    """Write transformed observations to a date-partitioned Parquet file."""
    run_timestamp = run_at or datetime.now(timezone.utc)
    partition_dir = Path(processed_dir) / (
        f"run_date={run_timestamp.strftime('%Y-%m-%d')}"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    output_path = partition_dir / (
        f"part-{run_timestamp.strftime('%Y%m%dT%H%M%SZ')}.parquet"
    )
    dataframe.to_parquet(output_path, index=False, engine="pyarrow")
    logger.info("Wrote %d observations to %s.", len(dataframe), output_path)
    return output_path
