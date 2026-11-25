from datetime import timedelta
import logging
import os

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag


logger = logging.getLogger(__name__)
WEATHERFLOW_CMD = os.environ.get("WEATHERFLOW_CMD", "python -m weatherflow")


def notify_failure(context) -> None:
    """Log an alert when a task exhausts its retries."""
    task_instance = context["task_instance"]
    logger.error(
        "ALERT: %s.%s failed after %s attempts.",
        task_instance.dag_id,
        task_instance.task_id,
        task_instance.try_number,
    )


@dag(
    schedule="0 * * * *",
    start_date=pendulum.datetime(2026, 11, 19, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "on_failure_callback": notify_failure,
    },
    tags=["weatherflow"],
)
def weatherflow_hourly():
    open_meteo = BashOperator(
        task_id="run_open_meteo",
        bash_command=f"{WEATHERFLOW_CMD} run --source open_meteo",
    )
    weatherapi = BashOperator(
        task_id="run_weatherapi",
        bash_command=f"{WEATHERFLOW_CMD} run --source weatherapi",
    )
    check_risk_alerts = BashOperator(
        task_id="check_risk_alerts",
        bash_command=f"{WEATHERFLOW_CMD} alerts",
    )

    [open_meteo, weatherapi] >> check_risk_alerts


weatherflow_hourly()
