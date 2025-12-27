"""Tests for specific coverage gaps in various modules.

This module contains targeted tests for uncovered lines identified during
code coverage analysis. Each test class focuses on a specific uncovered
scenario.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from filtarr.clients.sonarr import SonarrClient
from filtarr.config import Config, TagConfig
from filtarr.scheduler import IntervalTrigger
from filtarr.scheduler.exporter import _trigger_to_systemd_calendar
from filtarr.scheduler.triggers import trigger_to_cron_expression
from filtarr.state import StateManager
from filtarr.tagger import ReleaseTagger

# ============================================================================
# Tests for exporter.py L203 - Invalid cron expression format fallback
# ============================================================================


class TestExporterCronFallback:
    """Tests for exporter cron fallback when expression has wrong number of parts."""

    def test_cron_expression_with_wrong_parts_returns_fallback(self) -> None:
        """Should return fallback when cron expression doesn't have 5 parts."""
        from filtarr.scheduler import CronTrigger

        # Create a trigger with an expression that has wrong number of parts
        # We need to bypass validation, so we'll create it and modify it
        trigger = CronTrigger(expression="0 3 * * *")

        # Manually set expression to invalid format (only 3 parts)
        object.__setattr__(trigger, "expression", "0 3 *")

        calendar = _trigger_to_systemd_calendar(trigger)

        # Should return the fallback
        assert calendar == "*-*-* *:*:00"

    def test_cron_expression_with_six_parts_returns_fallback(self) -> None:
        """Should return fallback when cron expression has 6 parts."""
        from filtarr.scheduler import CronTrigger

        trigger = CronTrigger(expression="0 3 * * *")
        # Set to 6 parts
        object.__setattr__(trigger, "expression", "0 3 * * * *")

        calendar = _trigger_to_systemd_calendar(trigger)

        assert calendar == "*-*-* *:*:00"


# ============================================================================
# Tests for exporter.py L234 - Sub-60 second interval in systemd calendar
# ============================================================================


class TestExporterSubMinuteInterval:
    """Tests for exporter systemd calendar with sub-60 second intervals."""

    def test_interval_less_than_60_seconds_returns_seconds_format(self) -> None:
        """Should return seconds-based format for intervals < 60 seconds."""
        # Create a trigger with only seconds
        trigger = IntervalTrigger(seconds=30)

        calendar = _trigger_to_systemd_calendar(trigger)

        # Should contain seconds in format *-*-* *:*:00/30
        assert "00/30" in calendar


# ============================================================================
# Tests for sonarr.py L279-280 - Season parsing in update_series
# ============================================================================


class TestSonarrUpdateSeriesSeasonParsing:
    """Tests for season parsing in update_series response."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_series_parses_seasons_with_statistics(self) -> None:
        """Should parse seasons with statistics from update_series response."""
        series_data = {
            "id": 123,
            "title": "Test Series",
            "year": 2024,
            "monitored": True,
            "seasons": [
                {
                    "seasonNumber": 1,
                    "monitored": True,
                    "statistics": {
                        "episodeCount": 10,
                        "episodeFileCount": 8,
                    },
                },
                {
                    "seasonNumber": 2,
                    "monitored": False,
                    "statistics": {
                        "episodeCount": 5,
                        "episodeFileCount": 0,
                    },
                },
            ],
            "tags": [1, 2],
        }

        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(200, json=series_data)
        )
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(200, json=series_data)
        )
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(200, json=[series_data])
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-key") as client:
            series = await client.update_series(series_data)

        assert len(series.seasons) == 2
        assert series.seasons[0].episode_count == 10
        assert series.seasons[0].episode_file_count == 8
        assert series.seasons[1].episode_count == 5
        assert series.seasons[1].episode_file_count == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_series_parses_seasons_without_statistics(self) -> None:
        """Should handle seasons without statistics in update_series response."""
        series_data = {
            "id": 123,
            "title": "Test Series",
            "year": 2024,
            "monitored": True,
            "seasons": [
                {
                    "seasonNumber": 1,
                    "monitored": True,
                    # No statistics field
                },
            ],
            "tags": [],
        }

        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(200, json=series_data)
        )
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(200, json=series_data)
        )
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(200, json=[series_data])
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-key") as client:
            series = await client.update_series(series_data)

        # stats = s.get("statistics", {}) should return empty dict
        # stats.get("episodeCount", 0) should return 0
        assert len(series.seasons) == 1
        assert series.seasons[0].episode_count == 0
        assert series.seasons[0].episode_file_count == 0


# ============================================================================
# Tests for state.py L304-305 - OSError when saving state file
# ============================================================================


class TestStateSaveOSError:
    """Tests for OSError handling when saving state file."""

    def test_save_logs_error_on_oserror(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log error when save fails with OSError."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)
        manager.load()

        # Record something so state is dirty
        manager.record_check("movie", 1, True)

        # Mock open to raise OSError
        with (
            caplog.at_level(logging.ERROR, logger="filtarr.state"),
            patch("pathlib.Path.open", side_effect=OSError("Permission denied")),
        ):
            manager.save()

        # Should have logged the error
        assert any("Failed to save state file" in record.message for record in caplog.records)
        assert any("Permission denied" in record.message for record in caplog.records)


# ============================================================================
# Tests for tagger.py L124 - Return empty list for unknown item type
# ============================================================================


class MockClientNoMethods:
    """Mock client without get_movie_raw or get_series_raw methods."""

    def __init__(self) -> None:
        self.get_tags = AsyncMock(return_value=[])
        self.create_tag = AsyncMock()
        self.add_tag_to_item = AsyncMock()
        self.remove_tag_from_item = AsyncMock()


class TestTaggerUnknownItemType:
    """Tests for tagger returning empty list for unknown item type."""

    @pytest.mark.asyncio
    async def test_get_item_tag_ids_returns_empty_for_client_without_movie_method(
        self,
    ) -> None:
        """Should return empty list when client lacks get_movie_raw method."""
        tagger = ReleaseTagger(TagConfig())
        client = MockClientNoMethods()

        # Call _get_item_tag_ids with a client that doesn't have the required methods
        result = await tagger._get_item_tag_ids(client, 123, "movie")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_item_tag_ids_returns_empty_for_client_without_series_method(
        self,
    ) -> None:
        """Should return empty list when client lacks get_series_raw method."""
        tagger = ReleaseTagger(TagConfig())
        client = MockClientNoMethods()

        # For series type - client doesn't have get_series_raw
        result = await tagger._get_item_tag_ids(client, 123, "series")

        assert result == []


# ============================================================================
# Tests for base.py L291 - Debug log for 2-5 second requests
# ============================================================================


class TestBaseClientMediumSlowRequest:
    """Tests for debug logging of 2-5 second requests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_logs_debug_for_medium_slow_request(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should log debug for requests taking 2-5 seconds."""
        from filtarr.clients.radarr import RadarrClient

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        # Mock time.monotonic to simulate 3 seconds elapsed
        call_count = 0

        def mock_monotonic() -> float:
            nonlocal call_count
            call_count += 1
            # First call returns 0, second call returns 3.0 (simulating 3 seconds)
            if call_count == 1:
                return 0.0
            return 3.0

        with (
            caplog.at_level(logging.DEBUG, logger="filtarr.clients.base"),
            patch.object(time, "monotonic", mock_monotonic),
        ):
            async with RadarrClient("http://localhost:7878", "test-api-key") as client:
                await client.get_movie_releases(123)

        # Should have logged debug message for 2-5 second request
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("3.00s" in r.message for r in debug_records)
        assert any("/api/v3/release" in r.message for r in debug_records)


# ============================================================================
# Tests for config.py L34 - Docker /config directory detection
# ============================================================================


class TestConfigDockerPath:
    """Tests for Docker /config directory detection."""

    def test_get_config_base_path_returns_docker_config_when_exists(self, tmp_path: Path) -> None:
        """Should return /config when it exists as a directory."""
        from filtarr.config import _get_config_base_path

        # Create a mock /config directory
        docker_config = tmp_path / "config"
        docker_config.mkdir()

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("filtarr.config.Path") as mock_path_class,
        ):
            # Make Path("/config") return our test directory
            def path_constructor(path: str) -> Path:
                if path == "/config":
                    return docker_config
                return Path(path)

            mock_path_class.side_effect = path_constructor
            mock_path_class.home.return_value = tmp_path

            result = _get_config_base_path()

        # When /config is a directory, it should be returned
        assert result == docker_config


# ============================================================================
# Tests for config.py L681 - FILTARR_CONFIG_FILE env variable
# ============================================================================


class TestConfigFileEnvVariable:
    """Tests for FILTARR_CONFIG_FILE environment variable."""

    def test_filtarr_config_file_env_overrides_default_path(self, tmp_path: Path) -> None:
        """Should use FILTARR_CONFIG_FILE path when env var is set."""
        # Create a config file at a custom path
        custom_config = tmp_path / "custom" / "my-config.toml"
        custom_config.parent.mkdir(parents=True)
        custom_config.write_text("""
[radarr]
url = "http://localhost:7878"
api_key = "custom-file-key"
""")

        with (
            patch.object(Path, "home", return_value=tmp_path / "fake_home"),
            patch.dict(
                os.environ,
                {"FILTARR_CONFIG_FILE": str(custom_config)},
                clear=True,
            ),
        ):
            config = Config.load()

        assert config.radarr is not None
        assert config.radarr.api_key == "custom-file-key"

    def test_filtarr_config_file_nonexistent_uses_defaults(self, tmp_path: Path) -> None:
        """Should use defaults when FILTARR_CONFIG_FILE points to nonexistent file."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict(
                os.environ,
                {"FILTARR_CONFIG_FILE": "/nonexistent/config.toml"},
                clear=True,
            ),
        ):
            config = Config.load()

        # Should have defaults (no radarr/sonarr configured)
        assert config.radarr is None
        assert config.sonarr is None


# ============================================================================
# Tests for triggers.py L201 - Sub-minute interval returns "* * * * *"
# Note: This line is technically dead code because validation prevents
# all-zero intervals. We test it by bypassing validation.
# ============================================================================


class TestTriggersSubMinuteInterval:
    """Tests for sub-minute interval cron conversion."""

    def test_sub_minute_interval_with_bypassed_validation(self) -> None:
        """Should return '* * * * *' when total_minutes is 0 (bypassing validation)."""
        # Create a valid trigger first
        trigger = IntervalTrigger(seconds=30)

        # Manually set seconds to 0 to bypass validation
        # This simulates an edge case where total_minutes could be 0
        object.__setattr__(trigger, "seconds", 0)
        object.__setattr__(trigger, "minutes", 0)
        object.__setattr__(trigger, "hours", 0)
        object.__setattr__(trigger, "days", 0)
        object.__setattr__(trigger, "weeks", 0)

        cron = trigger_to_cron_expression(trigger)

        # Sub-minute intervals should run every minute
        assert cron == "* * * * *"

    def test_seconds_only_trigger_returns_every_1_minute_cron(self) -> None:
        """Should return '*/1 * * * *' when only seconds are specified."""
        # When seconds > 0, total_minutes = 1 (rounds up)
        trigger = IntervalTrigger(seconds=45)

        cron = trigger_to_cron_expression(trigger)

        # 45 seconds rounds up to 1 minute
        assert cron == "*/1 * * * *"
