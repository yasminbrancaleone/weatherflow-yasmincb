from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg
import streamlit as st

from weatherflow.config import ConfigurationError, get_database_url, load_config
from weatherflow.dashboard_data import load_dashboard_data


st.set_page_config(page_title="WeatherFlow outdoor work risk", layout="wide")
st.title("Where is outdoor work risky in the next 24 hours?")
st.caption(
    "Forecast risk is shown by city, hour, and source. "
    "Both providers remain visible when their readings disagree."
)


@st.cache_data(ttl=300)
def get_dashboard_data(
    database_url: str,
    city: str,
    threshold_c: float,
    dq_report_directory: str,
):
    return load_dashboard_data(
        database_url,
        city,
        threshold_c,
        Path(dq_report_directory),
    )


try:
    config = load_config()
    database_url = get_database_url()
    if not database_url:
        raise ConfigurationError(
            "Set DATABASE_URL in the project .env file before starting the dashboard."
        )

    city_names = [city["name"] for city in config["cities"]]
    selected_city = st.selectbox("Compare sources for", city_names)
    dq_config = config["dq"]
    threshold = dq_config["cross_source_temperature_tolerance_c"]
    report_directory = config["paths"]["dq_report_dir"]
    data = get_dashboard_data(
        database_url,
        selected_city,
        threshold,
        str(report_directory),
    )
except (ConfigurationError, OSError, psycopg.Error) as error:
    st.error(
        f"Dashboard data could not be loaded ({type(error).__name__}). "
        "Check DATABASE_URL, the warehouse, and the latest DQ report."
    )
    st.stop()

latest_ingested = data["latest_ingested_at_utc"]
if latest_ingested is None:
    st.warning("No weather observations are loaded yet.")
else:
    latest_utc = pd.Timestamp(latest_ingested).tz_convert("UTC")
    latest_london = latest_utc.tz_convert("Europe/London")
    freshness_column, quality_column = st.columns(2)
    freshness_column.metric(
        "Data as of (UK time)",
        latest_london.strftime("%d %b %Y, %H:%M %Z"),
    )
    age_hours = (
        datetime.now(timezone.utc) - latest_utc.to_pydatetime()
    ).total_seconds() / 3600
    if age_hours > dq_config["timeliness_hours"]:
        freshness_column.warning(
            "Data is stale; do not treat the displayed forecast as current."
        )

    dq_summary = data["dq_summary"]
    if dq_summary is None:
        quality_column.info("No DQ report has been generated yet.")
    else:
        quality_column.metric(
            "Latest DQ checks passed",
            dq_summary["passed_checks"],
        )
        quality_column.metric(
            "Rows quarantined",
            dq_summary["quarantined_rows"],
        )

st.subheader("Next 24 hours")
risks = data["upcoming_risks"]
if risks.empty:
    st.info("No forecast observations are available for the next 24 hours.")
else:
    risk_table = risks[
        [
            "city_name",
            "observed_at_london",
            "source",
            "outdoor_work_risk",
            "category",
            "beaufort_scale",
            "precipitation_mm",
        ]
    ].rename(
        columns={
            "city_name": "City",
            "observed_at_london": "Hour (UK)",
            "source": "Source",
            "outdoor_work_risk": "Outdoor work risk",
            "category": "Weather",
            "beaufort_scale": "Beaufort",
            "precipitation_mm": "Precipitation (mm)",
        }
    )
    styled_risks = risk_table.style.apply(
        lambda values: [
            {
                "high": "color: #b42318; font-weight: bold",
                "medium": "color: #b54708; font-weight: bold",
                "low": "color: #027a48; font-weight: bold",
            }.get(str(value).lower(), "")
            for value in values
        ],
        subset=["Outdoor work risk"],
    )
    st.dataframe(styled_risks, use_container_width=True, hide_index=True)

st.subheader("Seven-day trends by city")
trends = data["trends"]
if trends.empty:
    st.info("Seven-day trends will appear after weather data is loaded.")
else:
    temperature_trend, wind_trend = st.columns(2)
    trend_temperature = trends.pivot(
        index="observed_at_london",
        columns="city_name",
        values="temperature_c",
    )
    trend_wind = trends.pivot(
        index="observed_at_london",
        columns="city_name",
        values="wind_speed_kmh",
    )
    temperature_trend.markdown("**Temperature (°C)**")
    temperature_trend.line_chart(trend_temperature)
    wind_trend.markdown("**Wind speed (km/h)**")
    wind_trend.line_chart(trend_wind)
    st.caption("Trend values average the available source readings per city and hour.")

st.subheader(f"Source comparison: {selected_city}")
comparisons = data["source_comparison"]
if comparisons.empty:
    st.info("No paired source forecasts are available for this city in the next 24 hours.")
else:
    disagreement_count = int(comparisons["disagreement"].sum())
    st.metric(
        f"Hours differing by more than {threshold:g} °C",
        disagreement_count,
    )
    comparison_table = comparisons[
        [
            "observed_at_london",
            "open_meteo_temperature_c",
            "weatherapi_temperature_c",
            "temperature_difference_c",
            "disagreement",
        ]
    ].rename(
        columns={
            "observed_at_london": "Hour (UK)",
            "open_meteo_temperature_c": "Open-Meteo (°C)",
            "weatherapi_temperature_c": "WeatherAPI (°C)",
            "temperature_difference_c": "Difference (°C)",
            "disagreement": "Beyond threshold",
        }
    )
    comparison_table["Beyond threshold"] = comparison_table[
        "Beyond threshold"
    ].map({True: "Yes", False: "No"})
    st.dataframe(comparison_table, use_container_width=True, hide_index=True)
