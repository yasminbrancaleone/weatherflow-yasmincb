import argparse
import logging
from collections.abc import Sequence
from datetime import date, timedelta

from .pipeline import run as run_pipeline


logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure the application-wide logging format and level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="weatherflow",
        description="Run the WeatherFlow data pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Run the weather data pipeline.")
    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Backfill historical weather data.",
    )
    backfill_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backfill; the end date defaults to today minus 5 days.",
    )
    backfill_parser.add_argument("--start-date", type=date.fromisoformat)
    backfill_parser.add_argument("--end-date", type=date.fromisoformat)
    return parser


def resolve_backfill_dates(
    arguments: argparse.Namespace,
) -> tuple[date, date]:
    """Resolve backfill boundaries from CLI arguments."""
    default_end = date.today() - timedelta(days=5)

    if arguments.start_date and arguments.end_date:
        start_date = arguments.start_date
        end_date = arguments.end_date
    elif arguments.start_date:
        start_date = arguments.start_date
        end_date = default_end
    elif arguments.end_date:
        start_date = arguments.end_date - timedelta(days=arguments.days - 1)
        end_date = arguments.end_date
    else:
        end_date = default_end
        start_date = end_date - timedelta(days=arguments.days - 1)

    if start_date > end_date:
        raise ValueError("Backfill start-date must be on or before end-date.")
    if arguments.days < 1:
        raise ValueError("Backfill --days must be at least 1.")
    return start_date, end_date


def main(argv: Sequence[str] | None = None) -> int:
    """Parse command-line arguments and execute the selected command."""
    configure_logging()
    arguments = create_parser().parse_args(argv)

    if arguments.command == "run":
        run_pipeline()
        return 0

    if arguments.command == "backfill":
        start_date, end_date = resolve_backfill_dates(arguments)
        logger.info(
            "Backfill requested for %s through %s.",
            start_date.isoformat(),
            end_date.isoformat(),
        )
        return 0

    raise ValueError(f"Unsupported command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
