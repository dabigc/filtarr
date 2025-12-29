"""Logging utilities with sensitive data filtering.

This module provides logging configuration that automatically filters sensitive
data (like API keys) from log messages to prevent credential leakage.

Usage
-----
Apply the filter to all root handlers::

    from filtarr.logging import configure_logging

    configure_logging()

Or add the filter to specific handlers::

    from filtarr.logging import SensitiveDataFilter

    handler = logging.StreamHandler()
    handler.addFilter(SensitiveDataFilter())
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

# Map of string log level names to logging constants
LOG_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def parse_log_level(level: str | int) -> int:
    """Convert a log level string or int to a logging level constant.

    Args:
        level: Log level as string (e.g., "DEBUG", "INFO") or int.

    Returns:
        The logging level constant (e.g., logging.DEBUG).

    Raises:
        ValueError: If the string level is not recognized.
    """
    if isinstance(level, int):
        return level

    level_upper = level.upper()
    if level_upper not in LOG_LEVEL_MAP:
        valid_levels = ", ".join(sorted(LOG_LEVEL_MAP.keys()))
        raise ValueError(f"Invalid log level: {level}. Valid options: {valid_levels}")

    return LOG_LEVEL_MAP[level_upper]


class SensitiveDataFilter(logging.Filter):
    """Filter that redacts sensitive data from log messages.

    This filter automatically detects and masks API keys and other
    credentials in log messages to prevent accidental exposure.

    Patterns detected:
        - api_key=... or api-key=...
        - X-Api-Key: ... headers
        - "api_key": "..." in JSON-style strings

    Example
    -------
    >>> import logging
    >>> handler = logging.StreamHandler()
    >>> handler.addFilter(SensitiveDataFilter())
    >>> logger = logging.getLogger(__name__)
    >>> logger.addHandler(handler)
    >>> logger.warning("Request with api_key=secret123")  # Logs: "api_key=***"
    """

    PATTERNS: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        # Match X-Api-Key header style (must come before generic api_key pattern)
        (re.compile(r'X-Api-Key["\s:=]+["\']?[\w-]+', re.I), "X-Api-Key: ***"),
        # Match api_key or api-key followed by = or : and optional quotes, then value
        (re.compile(r'api[_-]?key["\s:=]+["\']?[\w-]+', re.I), "api_key=***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter the log record by redacting sensitive data.

        Args:
            record: The log record to filter.

        Returns:
            Always returns True (record is always emitted, just with redacted data).
        """
        if isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)

        # Also handle args that might contain sensitive data
        if record.args:
            filtered_args: list[object] = []
            for arg in record.args:
                if isinstance(arg, str):
                    filtered_arg = arg
                    for pattern, replacement in self.PATTERNS:
                        filtered_arg = pattern.sub(replacement, filtered_arg)
                    filtered_args.append(filtered_arg)
                else:
                    filtered_args.append(arg)
            record.args = tuple(filtered_args)

        return True


def configure_logging(
    level: str | int = logging.INFO,
    format_string: str | None = None,
) -> None:
    """Configure logging with sensitive data filtering.

    This function sets up the root logger with a handler that automatically
    filters out sensitive information like API keys.

    Args:
        level: The logging level to use. Can be a string (e.g., "DEBUG", "INFO")
            or an int (e.g., logging.DEBUG). Defaults to INFO.
        format_string: Optional custom format string for log messages.
            Defaults to "%(asctime)s - %(name)s - %(levelname)s - %(message)s".

    Example
    -------
    >>> from filtarr.logging import configure_logging
    >>> configure_logging(level=logging.DEBUG)
    >>> configure_logging(level="DEBUG")  # Also works with strings
    >>> # Now all log messages will have credentials filtered
    """
    # Convert string level to int if needed
    log_level = parse_log_level(level)

    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Create a handler with the filter
    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(format_string))
    handler.addFilter(SensitiveDataFilter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Suppress third-party library noise at INFO and above
    if log_level > logging.DEBUG:
        third_party_loggers = ["httpx", "uvicorn", "uvicorn.access", "uvicorn.error"]
        for logger_name in third_party_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)


def add_filter_to_existing_handlers() -> None:
    """Add the SensitiveDataFilter to all existing root handlers.

    This is useful when you want to add credential filtering to
    an already-configured logging setup.

    Example
    -------
    >>> import logging
    >>> logging.basicConfig(level=logging.INFO)
    >>> from filtarr.logging import add_filter_to_existing_handlers
    >>> add_filter_to_existing_handlers()
    >>> # Now existing handlers will filter credentials
    """
    sensitive_filter = SensitiveDataFilter()
    for handler in logging.root.handlers:
        handler.addFilter(sensitive_filter)
