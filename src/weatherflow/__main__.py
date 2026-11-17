import argparse
import logging
from collections.abc import Sequence

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse command-line arguments and execute the selected command."""
    configure_logging()
    arguments = create_parser().parse_args(argv)

    if arguments.command == "run":
        run_pipeline()
        return 0

    raise ValueError(f"Unsupported command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
