"""Tests for CLI global logging configuration."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from filtarr.checker import SamplingStrategy, SearchResult
from filtarr.cli import app
from filtarr.config import Config, RadarrConfig, SonarrConfig

runner = CliRunner()


def _create_mock_state_manager() -> MagicMock:
    """Create a mock StateManager for testing."""
    mock = MagicMock()
    mock.record_check = MagicMock()
    mock.get_stale_unavailable_items = MagicMock(return_value=[])
    mock.is_recently_checked = MagicMock(return_value=False)
    mock.get_cached_result = MagicMock(return_value=None)
    return mock


class TestGlobalLogLevel:
    """Tests for global --log-level flag."""

    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_flag_configures_logging(self, mock_configure: MagicMock) -> None:
        """Global --log-level flag should configure logging before command runs."""
        result = runner.invoke(app, ["--log-level", "debug", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()
        call_args = mock_configure.call_args
        # Check level was passed (either positional or keyword)
        assert "debug" in str(call_args).lower() or str(logging.DEBUG) in str(call_args)

    @patch("filtarr.cli.configure_logging")
    def test_global_log_level_short_flag(self, mock_configure: MagicMock) -> None:
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
    def test_global_log_level_case_insensitive(self, mock_configure: MagicMock) -> None:
        """Log level should be case insensitive."""
        result = runner.invoke(app, ["--log-level", "DEBUG", "version"])

        assert result.exit_code == 0
        mock_configure.assert_called_once()


class TestLogLevelPriority:
    """Tests for log level priority chain: CLI > env > config > default."""

    @patch("filtarr.cli.configure_logging")
    @patch.dict("os.environ", {"FILTARR_LOG_LEVEL": "warning"})
    def test_cli_overrides_env_var(self, mock_configure: MagicMock) -> None:
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
    def test_env_overrides_config(
        self, mock_config_load: MagicMock, mock_configure: MagicMock
    ) -> None:
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
    def test_config_overrides_default(
        self, mock_config_load: MagicMock, mock_configure: MagicMock
    ) -> None:
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
        _mock_configure: MagicMock,
        mock_config_load: MagicMock,
        mock_run_server: MagicMock,
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


class TestCleanLogOutput:
    """Tests that log output is clean at INFO level (no httpx noise)."""

    def test_batch_output_is_clean_at_info(self) -> None:
        """At INFO level, batch output should not include httpx log messages."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_movie_result = SearchResult(item_id=123, item_type="movie", has_match=True)

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker") as mock_get_checker,
            patch("filtarr.cli._fetch_movies_to_check") as mock_fetch,
        ):
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = mock_movie_result
            mock_get_checker.return_value = mock_checker
            # Return one movie to check
            mock_fetch.return_value = ([("movie", "123")], {"movie:123"})

            result = runner.invoke(
                app,
                ["--log-level", "info", "check", "batch", "--all-movies"],
            )

        # Verify no httpx log lines appear in output
        # httpx logs specifically contain patterns like "HTTP Request:" or "httpx - INFO"
        # Note: We check for specific log patterns, not just the word "httpx" which
        # might appear in error tracebacks that reference httpx module paths
        assert "HTTP Request:" not in result.output
        assert "httpx - INFO" not in result.output
        assert "httpx - DEBUG" not in result.output

    def test_check_movie_output_is_clean_at_info(self) -> None:
        """At INFO level, check movie output should not include httpx log messages."""
        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))

        async def mock_check_movie(_movie_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_movie = mock_check_movie
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(
                app,
                ["--log-level", "info", "check", "movie", "123"],
            )

        # Verify no httpx log lines appear in output (specific log patterns)
        # Note: We don't check for "httpx" generally as it may appear in error
        # tracebacks from httpx module paths
        assert "HTTP Request:" not in result.output
        assert "httpx - INFO" not in result.output
        assert "httpx - DEBUG" not in result.output

    def test_check_series_output_is_clean_at_info(self) -> None:
        """At INFO level, check series output should not include httpx log messages."""
        mock_result = SearchResult(
            item_id=456,
            item_type="series",
            has_match=True,
            strategy_used=SamplingStrategy.RECENT,
        )
        mock_config = Config(sonarr=SonarrConfig(url="http://localhost:8989", api_key="key"))

        async def mock_check_series(_series_id: int, **_kwargs: object) -> SearchResult:
            return mock_result

        mock_checker = MagicMock()
        mock_checker.check_series = mock_check_series
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_checker", return_value=mock_checker),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
        ):
            result = runner.invoke(
                app,
                ["--log-level", "info", "check", "series", "456"],
            )

        # Verify no httpx log lines appear in output (specific log patterns)
        assert "HTTP Request:" not in result.output
        assert "httpx - INFO" not in result.output
        assert "httpx - DEBUG" not in result.output
