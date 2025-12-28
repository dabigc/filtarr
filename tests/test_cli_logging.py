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


class TestLogLevelPriority:
    """Tests for log level priority chain: CLI > env > config > default."""

    @patch("filtarr.cli.configure_logging")
    @patch.dict("os.environ", {"FILTARR_LOG_LEVEL": "warning"})
    def test_cli_overrides_env_var(self, mock_configure: patch) -> None:
        """CLI flag should override environment variable."""
        result = runner.invoke(app, ["--log-level", "debug", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        # Verify debug was used, not warning from env
        call_args = str(mock_configure.call_args)
        assert "debug" in call_args.lower()

    @patch("filtarr.cli.configure_logging")
    @patch("filtarr.cli.Config.load")
    @patch.dict("os.environ", {"FILTARR_LOG_LEVEL": "error"}, clear=False)
    def test_env_overrides_config(self, mock_config_load: patch, mock_configure: patch) -> None:
        """Environment variable should override config file."""
        from filtarr.config import Config, LoggingConfig

        mock_config = Config(logging=LoggingConfig(level="debug"))
        mock_config_load.return_value = mock_config

        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        # Verify error from env was used, not debug from config
        call_args = str(mock_configure.call_args)
        assert "error" in call_args.lower()

    @patch("filtarr.cli.configure_logging")
    @patch("filtarr.cli.Config.load")
    @patch.dict("os.environ", {}, clear=True)
    def test_config_overrides_default(self, mock_config_load: patch, mock_configure: patch) -> None:
        """Config file should override default when no CLI or env."""
        import os

        from filtarr.config import Config, LoggingConfig

        # Clear FILTARR_LOG_LEVEL if present
        os.environ.pop("FILTARR_LOG_LEVEL", None)

        mock_config = Config(logging=LoggingConfig(level="warning"))
        mock_config_load.return_value = mock_config

        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        call_args = str(mock_configure.call_args)
        assert "warning" in call_args.lower()


class TestServeUsesGlobalLogLevel:
    """Tests that serve command uses global log level from context."""

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    @patch("filtarr.cli.configure_logging")
    def test_serve_uses_context_log_level(
        self,
        _mock_configure: patch,
        mock_config_load: patch,
        mock_run_server: patch,
    ) -> None:
        """Serve should get log level from context, not its own flag."""
        from filtarr.config import Config, RadarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        # Use global flag, not serve-specific flag
        runner.invoke(app, ["--log-level", "debug", "serve"])

        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("log_level") == "DEBUG"
