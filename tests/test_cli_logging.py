"""Tests for CLI global logging configuration."""

import logging
from unittest.mock import patch

from typer.testing import CliRunner

from filtarr.cli import app

runner = CliRunner()


class TestGlobalLogLevel:
    """Tests for global --log-level flag."""

    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_flag_configures_logging(self, mock_configure: patch) -> None:
        """Global --log-level flag should configure logging before command runs."""
        result = runner.invoke(app, ["--log-level", "debug", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        call_args = mock_configure.call_args
        # Check level was passed (either positional or keyword)
        assert "debug" in str(call_args).lower() or logging.DEBUG in str(call_args)

    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_short_flag(self, mock_configure: patch) -> None:
        """Short -l flag should work as alias for --log-level."""
        result = runner.invoke(app, ["-l", "warning", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()

    def test_global_log_level_invalid_exits_with_error(self) -> None:
        """Invalid log level should exit with error."""
        result = runner.invoke(app, ["--log-level", "verbose", "version"])

        assert result.exit_code == 1
        assert "invalid" in result.output.lower() or "verbose" in result.output.lower()

    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_case_insensitive(self, mock_configure: patch) -> None:
        """Log level should be case insensitive."""
        result = runner.invoke(app, ["--log-level", "DEBUG", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
