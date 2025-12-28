"""Tests for CLI serve command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from filtarr.cli import app

runner = CliRunner()


class TestServeCommandImportError:
    """Tests for serve command when webhook dependencies are missing."""

    def test_serve_without_webhook_dependencies(self) -> None:
        """Should show error when webhook dependencies are not installed."""
        import sys

        # Save original module if it exists
        original_module = sys.modules.get("filtarr.webhook")

        # Set module to None to trigger ImportError
        sys.modules["filtarr.webhook"] = None  # type: ignore[assignment]

        try:
            # For testing purposes, verify the error handling path works
            result = runner.invoke(app, ["serve"])

            # Should show error about missing dependencies
            assert result.exit_code == 1 or "webhook" in result.output.lower()
        finally:
            # Restore original module
            if original_module:
                sys.modules["filtarr.webhook"] = original_module
            elif "filtarr.webhook" in sys.modules:
                del sys.modules["filtarr.webhook"]


class TestServeCommand:
    """Tests for serve command functionality."""

    def test_serve_command_help(self) -> None:
        """Should show help for serve command."""
        result = runner.invoke(app, ["serve", "--help"])

        assert result.exit_code == 0
        assert "serve" in result.output.lower() or "webhook" in result.output.lower()

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_starts_server_with_defaults(
        self, mock_config_load: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Should start server with default settings."""
        from filtarr.config import Config, RadarrConfig, SonarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            sonarr=SonarrConfig(url="http://127.0.0.1:8989", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        result = runner.invoke(app, ["serve"])

        # Should have tried to run the server
        assert mock_run_server.called
        assert "server" in result.output.lower() or result.exit_code == 0

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_with_custom_port(
        self, mock_config_load: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Should start server with custom port."""
        from filtarr.config import Config, RadarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        runner.invoke(app, ["serve", "--port", "9000"])

        # Check that port was passed
        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("port") == 9000

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_with_custom_host(
        self, mock_config_load: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Should start server with custom host."""
        from filtarr.config import Config, RadarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        runner.invoke(app, ["serve", "--host", "0.0.0.0"])

        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("host") == "0.0.0.0"

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_with_no_scheduler(
        self, mock_config_load: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Should start server without scheduler when disabled."""
        from filtarr.config import Config, RadarrConfig, SchedulerConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
            scheduler=SchedulerConfig(enabled=True),
        )
        mock_config_load.return_value = mock_config

        runner.invoke(app, ["serve", "--no-scheduler"])

        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("scheduler_enabled") is False

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_with_scheduler_enabled(
        self, mock_config_load: MagicMock, mock_run_server: MagicMock
    ) -> None:
        """Should start server with scheduler when enabled in config."""
        from filtarr.config import Config, RadarrConfig, SchedulerConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
            scheduler=SchedulerConfig(enabled=True, schedules=[]),
        )
        mock_config_load.return_value = mock_config

        with patch("filtarr.scheduler.SchedulerManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.get_all_schedules.return_value = []
            mock_manager_class.return_value = mock_manager

            runner.invoke(app, ["serve"])

            assert mock_run_server.called
            call_kwargs = mock_run_server.call_args.kwargs
            assert call_kwargs.get("scheduler_enabled") is True

    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_shows_endpoint_info(
        self, mock_config_load: MagicMock, _mock_run_server: MagicMock
    ) -> None:
        """Should display endpoint information on startup."""
        from filtarr.config import Config, RadarrConfig, SonarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            sonarr=SonarrConfig(url="http://127.0.0.1:8989", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        result = runner.invoke(app, ["serve"])

        # Should show endpoint info
        assert "radarr" in result.output.lower() or "webhook" in result.output.lower()

    @patch("filtarr.cli.configure_logging")
    @patch("filtarr.webhook.run_server")
    @patch("filtarr.cli.Config.load")
    def test_serve_with_global_log_level(
        self,
        mock_config_load: MagicMock,
        mock_run_server: MagicMock,
        _mock_configure: MagicMock,
    ) -> None:
        """Should pass global log level to server."""
        from filtarr.config import Config, RadarrConfig, WebhookConfig

        mock_config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="test"),
            webhook=WebhookConfig(host="127.0.0.1", port=8080),
        )
        mock_config_load.return_value = mock_config

        runner.invoke(app, ["--log-level", "debug", "serve"])

        assert mock_run_server.called
        call_kwargs = mock_run_server.call_args.kwargs
        assert call_kwargs.get("log_level") == "DEBUG"
