"""Command-line entry point for the WeatherFlow package."""

import logging


logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure the application-wide logging format and level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
