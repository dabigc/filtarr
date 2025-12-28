"""Tests for logging utilities with sensitive data filtering."""

from __future__ import annotations

import logging

import pytest

from filtarr.logging import (
    SensitiveDataFilter,
    add_filter_to_existing_handlers,
    configure_logging,
    parse_log_level,
)


class TestSensitiveDataFilter:
    """Tests for SensitiveDataFilter class."""

    def test_filter_api_key_equals_format(self) -> None:
        """Should filter api_key=value format."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Request with api_key=secret123abc",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "secret123abc" not in record.msg
        assert "api_key=***" in record.msg

    def test_filter_api_key_colon_format(self) -> None:
        """Should filter api_key: value format."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Config: api_key: "my-secret-key"',
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "my-secret-key" not in record.msg

    def test_filter_api_hyphen_key_format(self) -> None:
        """Should filter api-key=value format."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Using api-key=abc123def",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "abc123def" not in record.msg
        assert "api_key=***" in record.msg

    def test_filter_apikey_no_separator_format(self) -> None:
        """Should filter apikey=value format (no separator)."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="apikey=supersecret",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "supersecret" not in record.msg
        assert "api_key=***" in record.msg

    def test_filter_x_api_key_header_format(self) -> None:
        """Should filter X-Api-Key: value header format."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Headers: X-Api-Key: abc123-def456",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "abc123-def456" not in record.msg
        assert "X-Api-Key: ***" in record.msg

    def test_filter_x_api_key_with_quotes(self) -> None:
        """Should filter X-Api-Key with quoted value."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg='Request with "X-Api-Key": "secret-key-value"',
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "secret-key-value" not in record.msg

    def test_filter_case_insensitive(self) -> None:
        """Should filter regardless of case."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="API_KEY=secret and Api_Key=another",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "secret" not in record.msg
        assert "another" not in record.msg

    def test_filter_preserves_non_sensitive_data(self) -> None:
        """Should preserve messages without sensitive data."""
        filter_ = SensitiveDataFilter()
        original_msg = "Normal log message without secrets"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=original_msg,
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert record.msg == original_msg

    def test_filter_always_returns_true(self) -> None:
        """Filter should always return True (emit the record)."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="api_key=secret",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True

    def test_filter_non_string_msg(self) -> None:
        """Should handle non-string messages gracefully."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=12345,  # Non-string message
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert record.msg == 12345

    def test_filter_args_with_sensitive_data(self) -> None:
        """Should filter sensitive data in args."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Request to %s with %s",
            args=("http://localhost", "api_key=secret123"),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "secret123" not in str(record.args)
        assert "api_key=***" in str(record.args)

    def test_filter_args_preserves_non_strings(self) -> None:
        """Should preserve non-string args unchanged."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Count: %d, Value: %s",
            args=(42, "normal_value"),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert record.args == (42, "normal_value")

    def test_filter_multiple_sensitive_values_in_message(self) -> None:
        """Should filter all sensitive values in a single message."""
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Radarr api_key=key1 and Sonarr api_key=key2",
            args=(),
            exc_info=None,
        )

        result = filter_.filter(record)

        assert result is True
        assert "key1" not in record.msg
        assert "key2" not in record.msg
        # Both should be replaced
        assert record.msg.count("api_key=***") == 2


class TestParseLogLevel:
    """Tests for parse_log_level function."""

    @pytest.mark.parametrize(
        ("level_string", "expected"),
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ],
    )
    def test_parse_valid_uppercase_levels(self, level_string: str, expected: int) -> None:
        """Should parse valid uppercase level strings."""
        assert parse_log_level(level_string) == expected

    @pytest.mark.parametrize(
        ("level_string", "expected"),
        [
            ("debug", logging.DEBUG),
            ("info", logging.INFO),
            ("warning", logging.WARNING),
            ("error", logging.ERROR),
            ("critical", logging.CRITICAL),
        ],
    )
    def test_parse_valid_lowercase_levels(self, level_string: str, expected: int) -> None:
        """Should parse valid lowercase level strings."""
        assert parse_log_level(level_string) == expected

    @pytest.mark.parametrize(
        ("level_string", "expected"),
        [
            ("Debug", logging.DEBUG),
            ("Info", logging.INFO),
            ("Warning", logging.WARNING),
            ("ErRoR", logging.ERROR),
            ("CrItIcAl", logging.CRITICAL),
        ],
    )
    def test_parse_valid_mixedcase_levels(self, level_string: str, expected: int) -> None:
        """Should parse valid mixed case level strings."""
        assert parse_log_level(level_string) == expected

    def test_parse_invalid_level_raises_value_error(self) -> None:
        """Should raise ValueError for invalid level string."""
        with pytest.raises(ValueError, match="Invalid log level: INVALID"):
            parse_log_level("INVALID")

    def test_parse_invalid_level_includes_valid_options_in_message(self) -> None:
        """Error message should list valid options."""
        with pytest.raises(ValueError, match=r"Valid options:.*DEBUG.*INFO.*WARNING"):
            parse_log_level("NOTVALID")

    @pytest.mark.parametrize(
        "level_int",
        [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
            42,  # Arbitrary integer should pass through unchanged
        ],
    )
    def test_parse_integer_levels_pass_through(self, level_int: int) -> None:
        """Should pass through integer levels unchanged."""
        assert parse_log_level(level_int) == level_int


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_adds_handler(self) -> None:
        """configure_logging should add a handler to root logger."""
        # Get initial handler count
        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        configure_logging(level=logging.DEBUG)

        assert len(root_logger.handlers) > initial_count

        # Cleanup: remove the added handler
        root_logger.handlers = root_logger.handlers[:initial_count]

    def test_configure_logging_handler_has_filter(self) -> None:
        """Configured handler should have SensitiveDataFilter."""
        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        configure_logging()

        # The last added handler should have our filter
        new_handler = root_logger.handlers[-1]
        filter_types = [type(f) for f in new_handler.filters]
        assert SensitiveDataFilter in filter_types

        # Cleanup
        root_logger.handlers = root_logger.handlers[:initial_count]

    def test_configure_logging_sets_level(self) -> None:
        """configure_logging should set the specified level."""
        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        configure_logging(level=logging.WARNING)

        assert root_logger.level == logging.WARNING

        # Cleanup
        root_logger.handlers = root_logger.handlers[:initial_count]
        root_logger.setLevel(logging.WARNING)  # Reset to default

    def test_configure_logging_custom_format(self) -> None:
        """configure_logging should use custom format string."""
        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        custom_format = "%(levelname)s: %(message)s"
        configure_logging(format_string=custom_format)

        new_handler = root_logger.handlers[-1]
        assert new_handler.formatter is not None
        assert new_handler.formatter._fmt == custom_format

        # Cleanup
        root_logger.handlers = root_logger.handlers[:initial_count]


class TestAddFilterToExistingHandlers:
    """Tests for add_filter_to_existing_handlers function."""

    def test_add_filter_to_existing_handlers(self) -> None:
        """Should add filter to all existing root handlers."""
        root_logger = logging.getLogger()

        # Add a test handler
        test_handler = logging.StreamHandler()
        root_logger.addHandler(test_handler)

        # Verify no filter initially
        assert not any(isinstance(f, SensitiveDataFilter) for f in test_handler.filters)

        add_filter_to_existing_handlers()

        # Now should have the filter
        assert any(isinstance(f, SensitiveDataFilter) for f in test_handler.filters)

        # Cleanup
        root_logger.removeHandler(test_handler)

    def test_add_filter_to_multiple_handlers(self) -> None:
        """Should add filter to all handlers, not just one."""
        root_logger = logging.getLogger()

        # Add multiple test handlers
        handler1 = logging.StreamHandler()
        handler2 = logging.StreamHandler()
        root_logger.addHandler(handler1)
        root_logger.addHandler(handler2)

        add_filter_to_existing_handlers()

        # Both should have the filter
        assert any(isinstance(f, SensitiveDataFilter) for f in handler1.filters)
        assert any(isinstance(f, SensitiveDataFilter) for f in handler2.filters)

        # Cleanup
        root_logger.removeHandler(handler1)
        root_logger.removeHandler(handler2)


class TestLoggingIntegration:
    """Integration tests for logging with real logger output."""

    def test_filtered_logging_redacts_api_key(self, caplog: pytest.LogCaptureFixture) -> None:
        """Real logging should redact API keys."""
        # Create a logger with our filter
        logger = logging.getLogger("test.integration")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

        with caplog.at_level(logging.INFO, logger="test.integration"):
            logger.info("Connecting with api_key=supersecret123")

        assert "supersecret123" not in caplog.text
        assert "api_key=***" in caplog.text

        # Cleanup
        logger.removeHandler(handler)

    def test_filtered_logging_redacts_header(self, caplog: pytest.LogCaptureFixture) -> None:
        """Real logging should redact X-Api-Key headers."""
        logger = logging.getLogger("test.integration2")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

        with caplog.at_level(logging.INFO, logger="test.integration2"):
            logger.info("Sending X-Api-Key: my-api-key-12345")

        assert "my-api-key-12345" not in caplog.text
        assert "X-Api-Key: ***" in caplog.text

        # Cleanup
        logger.removeHandler(handler)


class TestThirdPartyLoggerSuppression:
    """Tests for third-party logger suppression at different log levels."""

    def test_third_party_loggers_suppressed_at_info(self) -> None:
        """Third-party loggers should be WARNING+ at INFO level."""
        # Reset logging state
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

        # Reset third-party loggers to NOTSET before test
        third_party_loggers = ["httpx", "uvicorn", "uvicorn.access", "uvicorn.error"]
        for logger_name in third_party_loggers:
            logging.getLogger(logger_name).setLevel(logging.NOTSET)

        configure_logging(level="INFO")

        # Check that httpx and uvicorn loggers are set to WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("uvicorn").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
        assert logging.getLogger("uvicorn.error").level == logging.WARNING

    def test_third_party_loggers_verbose_at_debug(self) -> None:
        """Third-party loggers should be DEBUG at DEBUG level."""
        # Reset logging state
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

        # Reset third-party loggers to NOTSET before test
        third_party_loggers = ["httpx", "uvicorn", "uvicorn.access", "uvicorn.error"]
        for logger_name in third_party_loggers:
            logging.getLogger(logger_name).setLevel(logging.NOTSET)

        configure_logging(level="DEBUG")

        # At DEBUG, third-party loggers inherit from root (DEBUG)
        httpx_logger = logging.getLogger("httpx")
        # Level 0 means NOTSET (inherits from parent)
        assert httpx_logger.level in (logging.NOTSET, logging.DEBUG)
