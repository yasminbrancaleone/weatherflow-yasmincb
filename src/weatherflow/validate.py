"""Data quality checks for the WeatherFlow pipeline."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CheckResult:
    """Store the outcome of one data quality check."""

    name: str
    dimension: str
    severity: str
    passed: bool
    failed_rows: int
    details: str


class DataQualityError(RuntimeError):
    """Raised when a blocking data quality check fails."""


def _check(
    name: str,
    dimension: str,
    severity: str,
    bad_mask: pd.Series,
    details: str,
) -> CheckResult:
    """Build a row-level or dataset-level check result."""
    failed_rows = int(bad_mask.sum()) if len(bad_mask) else 0
    return CheckResult(
        name=name,
        dimension=dimension,
        severity=severity,
        passed=failed_rows == 0,
        failed_rows=failed_rows,
        details=details,
    )


def validate(
    dataframe: pd.DataFrame,
    config: dict[str, Any],
    run_mode: str = "incremental",
) -> tuple[pd.DataFrame, pd.DataFrame, list[CheckResult]]:
    """Validate data quality and return good, quarantined, and check results."""
    if dataframe.empty:
        empty_result = CheckResult(
            name="required_columns",
            dimension="completeness",
            severity="fail",
            passed=False,
            failed_rows=0,
            details="No rows were produced by the transform step.",
        )
        raise DataQualityError(empty_result.details)

    data = dataframe.copy()
    if "source" not in data.columns:
        data["source"] = "open-meteo"

    dq = config["dq"]
    reasons: dict[int, list[str]] = {
        index: [] for index in data.index
    }

    completeness_mask = data[
        ["city", "observed_at_utc", "temperature_c"]
    ].isna().any(axis=1)
    for index in data.index[completeness_mask]:
        reasons[index].append("missing_required_field")

    temperature_mask = data["temperature_c"].notna() & (
        data["temperature_c"].lt(dq["temperature_min_c"])
        | data["temperature_c"].gt(dq["temperature_max_c"])
    )
    for index in data.index[temperature_mask]:
        reasons[index].append("temperature_out_of_range")

    humidity_mask = data["humidity_pct"].notna() & (
        data["humidity_pct"].lt(dq["humidity_min_pct"])
        | data["humidity_pct"].gt(dq["humidity_max_pct"])
    )
    for index in data.index[humidity_mask]:
        reasons[index].append("humidity_out_of_range")

    precipitation_mask = data["precipitation_mm"].notna() & (
        data["precipitation_mm"].lt(dq["precipitation_min_mm"])
    )
    wind_mask = data["wind_speed_kmh"].notna() & (
        data["wind_speed_kmh"].lt(dq["wind_speed_min_kmh"])
    )
    nonnegative_mask = precipitation_mask | wind_mask
    for index in data.index[precipitation_mask]:
        reasons[index].append("negative_precipitation")
    for index in data.index[wind_mask]:
        reasons[index].append("negative_wind_speed")

    duplicate_mask = data.duplicated(
        subset=["city", "observed_at_utc", "source"], keep=False
    )
    if duplicate_mask.any():
        duplicate_count = int(duplicate_mask.sum())
        raise DataQualityError(
            "Duplicate (city, observed_at_utc, source) rows are not allowed "
            f"({duplicate_count} affected rows)."
        )

    consistency_mask = data["feels_like_c"].notna() & (
        data["temperature_c"].notna()
        & data["feels_like_c"].sub(data["temperature_c"]).abs().gt(
            dq["feels_like_tolerance_c"]
        )
    )

    observed_utc = pd.to_datetime(
        data["observed_at_utc"], format="mixed", utc=True
    )
    configured_cities = {city["name"] for city in config["cities"]}
    observed_hours = observed_utc.dt.floor("h").dropna().drop_duplicates()
    city_hour_pairs = pd.MultiIndex.from_product(
        [sorted(configured_cities), observed_hours],
        names=["city", "observed_hour"],
    )
    actual_pairs = pd.MultiIndex.from_arrays(
        [
            data["city"].astype(str),
            observed_utc.dt.floor("h"),
        ],
        names=["city", "observed_hour"],
    )
    missing_pairs = city_hour_pairs.difference(actual_pairs)
    coverage_failed = int(len(missing_pairs)) if run_mode == "full" else 0

    now = datetime.now(timezone.utc)
    past_or_current = observed_utc[observed_utc <= now]
    timeliness_failed = 0
    timeliness_passed = True
    if run_mode == "incremental" and not past_or_current.empty:
        latest_past = past_or_current.max()
        timeliness_failed = int(
            (now - latest_past).total_seconds() > dq["timeliness_hours"] * 3600
        )
        timeliness_passed = timeliness_failed == 0

    results = [
        _check(
            "required_fields",
            "completeness",
            "quarantine",
            completeness_mask,
            "city, observed_at_utc, and temperature_c must not be null.",
        ),
        _check(
            "temperature_range",
            "validity",
            "quarantine",
            temperature_mask,
            f"temperature_c must be between {dq['temperature_min_c']} "
            f"and {dq['temperature_max_c']} C.",
        ),
        _check(
            "humidity_range",
            "validity",
            "quarantine",
            humidity_mask,
            f"humidity_pct must be between {dq['humidity_min_pct']} "
            f"and {dq['humidity_max_pct']}.",
        ),
        _check(
            "nonnegative_measurements",
            "validity",
            "quarantine",
            nonnegative_mask,
            "precipitation_mm and wind_speed_kmh must be nonnegative.",
        ),
        CheckResult(
            name="unique_city_hour_source",
            dimension="uniqueness",
            severity="fail",
            passed=not duplicate_mask.any(),
            failed_rows=int(duplicate_mask.sum()),
            details="Duplicate (city, observed_at_utc, source) rows are not allowed.",
        ),
        CheckResult(
            name="configured_city_hour_coverage",
            dimension="completeness",
            severity="fail",
            passed=coverage_failed == 0,
            failed_rows=coverage_failed,
            details=(
                "Every configured city must have a row for every observed hour "
                "in a full run."
                if run_mode == "full"
                else "Full-run coverage check is not required for incremental runs."
            ),
        ),
        CheckResult(
            name="latest_observation_timeliness",
            dimension="timeliness",
            severity="warn",
            passed=timeliness_passed,
            failed_rows=timeliness_failed,
            details=(
                "Latest non-future observation must be within "
                f"{dq['timeliness_hours']} hours."
            ),
        ),
        _check(
            "apparent_temperature_consistency",
            "consistency",
            "warn",
            consistency_mask,
            "feels_like_c must be within "
            f"{dq['feels_like_tolerance_c']} C of temperature_c.",
        ),
    ]

    quarantine_mask = (
        completeness_mask
        | temperature_mask
        | humidity_mask
        | nonnegative_mask
    )
    quarantined = data.loc[quarantine_mask].copy()
    quarantined["dq_failure_reason"] = [
        "; ".join(reasons[index]) for index in quarantined.index
    ]
    good = data.loc[~quarantine_mask].copy()

    failed = [
        result
        for result in results
        if not result.passed and result.severity == "fail"
    ]
    if failed:
        details = "; ".join(
            f"{result.name}: {result.failed_rows} failed rows"
            for result in failed
        )
        raise DataQualityError(details)

    return good, quarantined, results
