"""
Structured logging setup for the 4RC backend.
Provides colored console output for dev and JSON format for production.
"""
import logging
import sys
from ..core.config import settings


class ColorFormatter(logging.Formatter):
    """Custom formatter with ANSI color codes for terminal output."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{self.BOLD}{record.levelname:<8}{self.RESET}"
        record.name = f"\033[34m{record.name}\033[0m"
        return super().format(record)


def setup_logging() -> None:
    """Configure application-wide logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler with color formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    if settings.DEBUG:
        formatter = ColorFormatter(
            fmt="%(asctime)s │ %(levelname)s │ %(name)s │ %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            fmt='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger for a module."""
    return logging.getLogger(f"4rc.{name}")
