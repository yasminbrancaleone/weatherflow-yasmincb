from datetime import datetime, timezone
import logging
from pathlib import Path

import pandas as pd


logger = logging.getLogger(__name__)


def write_processed_parquet(
    dataframe: pd.DataFrame,
    processed_dir: Path | str,
    run_at: datetime | None = None,
    suffix: str | None = None,
) -> Path:
    """Write transformed observations to a date-partitioned Parquet file."""
    run_timestamp = run_at or datetime.now(timezone.utc)
    partition_dir = Path(processed_dir) / (
        f"run_date={run_timestamp.strftime('%Y-%m-%d')}"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    suffix_text = f"-{suffix}" if suffix else ""
    output_path = partition_dir / (
        f"part-{run_timestamp.strftime('%Y%m%dT%H%M%SZ')}"
        f"{suffix_text}.parquet"
    )
    dataframe.to_parquet(output_path, index=False, engine="pyarrow")
    logger.info("Wrote %d observations to %s.", len(dataframe), output_path)
    return output_path


def write_quarantine(
    quarantined_rows: pd.DataFrame,
    quarantine_dir: Path | str,
    run_at: datetime | None = None,
) -> Path | None:
    """Write quarantined rows to a date-partitioned CSV file."""
    if quarantined_rows.empty:
        return None

    run_timestamp = run_at or datetime.now(timezone.utc)
    partition_dir = Path(quarantine_dir) / (
        f"run_date={run_timestamp.strftime('%Y-%m-%d')}"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    output_path = partition_dir / (
        f"quarantine-{run_timestamp.strftime('%Y%m%dT%H%M%SZ')}.csv"
    )
    quarantined_rows.to_csv(output_path, index=False)
    logger.warning(
        "Quarantined %d rows to %s.",
        len(quarantined_rows),
        output_path,
    )
    return output_path


def write_dq_report(
    check_results: list,
    report_dir: Path | str,
    good_rows: int,
    quarantined_rows: int,
    run_at: datetime | None = None,
    suffix: str | None = None,
) -> Path:
    """Write a Markdown summary of the latest data quality checks."""
    run_timestamp = run_at or datetime.now(timezone.utc)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    suffix_text = f"-{suffix}" if suffix else ""
    report_path = report_dir / (
        f"{run_timestamp.strftime('%Y%m%dT%H%M%SZ')}{suffix_text}.md"
    )

    lines = [
        "# Data Quality Report",
        "",
        f"- **Run timestamp (UTC):** {run_timestamp.isoformat()}",
        f"- **Good rows:** {good_rows}",
        f"- **Quarantined rows:** {quarantined_rows}",
        "",
        "| Check | Dimension | Severity | Status | Failed rows | Details |",
        "|---|---|---|---|---:|---|",
    ]
    for result in check_results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| {result.name} | {result.dimension} | {result.severity} | "
            f"{status} | {result.failed_rows} | {result.details} |"
        )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote DQ report to %s.", report_path)
    return report_path
