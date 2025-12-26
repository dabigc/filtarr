"""Tests for the scheduler module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from filtarr.config import Config, RadarrConfig, SchedulerConfig, SonarrConfig, TagConfig
from filtarr.scheduler import (
    CronTrigger,
    IntervalTrigger,
    RunStatus,
    ScheduleDefinition,
    ScheduleRunRecord,
    ScheduleTarget,
    SeriesStrategy,
    TriggerType,
    format_trigger_description,
    get_next_run_time,
    parse_interval_string,
    parse_trigger,
    trigger_to_cron_expression,
)
from filtarr.scheduler.executor import JobExecutor, execute_schedule
from filtarr.scheduler.exporter import (
    _get_filtarr_path,
    _schedule_to_batch_args,
    _trigger_to_systemd_calendar,
    export_cron,
    export_systemd,
    export_systemd_timer,
)
from filtarr.scheduler.manager import SchedulerManager, _to_float, _to_int
from filtarr.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path


class TestIntervalTrigger:
    """Tests for IntervalTrigger model."""

    def test_interval_trigger_valid(self) -> None:
        """Test creating a valid interval trigger."""
        trigger = IntervalTrigger(hours=6)
        assert trigger.type == TriggerType.INTERVAL
        assert trigger.hours == 6
        assert trigger.minutes == 0

    def test_interval_trigger_compound(self) -> None:
        """Test compound interval trigger."""
        trigger = IntervalTrigger(hours=2, minutes=30)
        assert trigger.hours == 2
        assert trigger.minutes == 30
        assert trigger.total_seconds() == 2 * 3600 + 30 * 60

    def test_interval_trigger_all_zeros_fails(self) -> None:
        """Test that all-zero interval fails validation."""
        with pytest.raises(ValueError, match="At least one interval component"):
            IntervalTrigger()

    def test_interval_trigger_total_seconds(self) -> None:
        """Test total_seconds calculation."""
        trigger = IntervalTrigger(weeks=1, days=2, hours=3, minutes=4, seconds=5)
        expected = (
            1 * 7 * 24 * 3600  # weeks
            + 2 * 24 * 3600  # days
            + 3 * 3600  # hours
            + 4 * 60  # minutes
            + 5  # seconds
        )
        assert trigger.total_seconds() == expected


class TestCronTrigger:
    """Tests for CronTrigger model."""

    def test_cron_trigger_valid(self) -> None:
        """Test creating a valid cron trigger."""
        trigger = CronTrigger(expression="0 3 * * *")
        assert trigger.type == TriggerType.CRON
        assert trigger.expression == "0 3 * * *"

    def test_cron_trigger_invalid_format(self) -> None:
        """Test that invalid cron expression fails."""
        with pytest.raises((ValueError, Exception)):
            CronTrigger(expression="invalid")


class TestScheduleDefinition:
    """Tests for ScheduleDefinition model."""

    def test_schedule_definition_minimal(self) -> None:
        """Test creating a schedule with minimal fields."""
        schedule = ScheduleDefinition(
            name="test-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        assert schedule.name == "test-schedule"
        assert schedule.target == ScheduleTarget.MOVIES
        assert schedule.enabled is True
        assert schedule.batch_size == 0
        assert schedule.delay == 0.5

    def test_schedule_definition_full(self) -> None:
        """Test creating a schedule with all fields."""
        schedule = ScheduleDefinition(
            name="full-schedule",
            enabled=False,
            target=ScheduleTarget.BOTH,
            trigger=CronTrigger(expression="0 3 * * 0"),
            batch_size=100,
            delay=1.0,
            skip_tagged=False,
            include_rechecks=False,
            no_tag=True,
            dry_run=True,
            strategy=SeriesStrategy.DISTRIBUTED,
            seasons=5,
        )
        assert schedule.name == "full-schedule"
        assert schedule.enabled is False
        assert schedule.batch_size == 100
        assert schedule.strategy == SeriesStrategy.DISTRIBUTED
        assert schedule.seasons == 5

    def test_schedule_name_normalized(self) -> None:
        """Test that schedule name is normalized to lowercase."""
        schedule = ScheduleDefinition(
            name="My-Schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=1),
        )
        assert schedule.name == "my-schedule"

    def test_schedule_name_invalid_chars(self) -> None:
        """Test that invalid characters in name fail validation."""
        with pytest.raises(ValueError):
            ScheduleDefinition(
                name="my schedule!",
                target=ScheduleTarget.MOVIES,
                trigger=IntervalTrigger(hours=1),
            )


class TestScheduleRunRecord:
    """Tests for ScheduleRunRecord model."""

    def test_run_record_completed(self) -> None:
        """Test creating a completed run record."""
        started = datetime.now(UTC)
        completed = started + timedelta(minutes=5)

        record = ScheduleRunRecord(
            schedule_name="test",
            started_at=started,
            completed_at=completed,
            status=RunStatus.COMPLETED,
            items_processed=100,
            items_with_4k=25,
        )

        assert record.status == RunStatus.COMPLETED
        assert record.items_processed == 100
        assert record.items_with_4k == 25
        assert record.duration_seconds() == pytest.approx(300, abs=1)

    def test_run_record_running(self) -> None:
        """Test running record has no duration."""
        record = ScheduleRunRecord(
            schedule_name="test",
            started_at=datetime.now(UTC),
            status=RunStatus.RUNNING,
        )
        assert record.duration_seconds() is None


class TestTriggerParsing:
    """Tests for trigger parsing functions."""

    def test_parse_trigger_interval(self) -> None:
        """Test parsing interval trigger from dict."""
        data = {"type": "interval", "hours": 6, "minutes": 30}
        trigger = parse_trigger(data)
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.hours == 6
        assert trigger.minutes == 30

    def test_parse_trigger_cron(self) -> None:
        """Test parsing cron trigger from dict."""
        data = {"type": "cron", "expression": "0 3 * * *"}
        trigger = parse_trigger(data)
        assert isinstance(trigger, CronTrigger)
        assert trigger.expression == "0 3 * * *"

    def test_parse_trigger_invalid_type(self) -> None:
        """Test parsing unknown trigger type fails."""
        with pytest.raises(ValueError, match="Unknown trigger type"):
            parse_trigger({"type": "unknown"})

    def test_parse_interval_string_hours(self) -> None:
        """Test parsing interval string with hours."""
        trigger = parse_interval_string("6h")
        assert trigger.hours == 6

    def test_parse_interval_string_compound(self) -> None:
        """Test parsing compound interval string."""
        trigger = parse_interval_string("2h30m")
        assert trigger.hours == 2
        assert trigger.minutes == 30

    def test_parse_interval_string_full_words(self) -> None:
        """Test parsing interval with full words."""
        trigger = parse_interval_string("30 minutes")
        assert trigger.minutes == 30

    def test_parse_interval_string_invalid(self) -> None:
        """Test parsing invalid interval string fails."""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval_string("invalid")


class TestTriggerConversion:
    """Tests for trigger conversion functions."""

    def test_trigger_to_cron_from_cron(self) -> None:
        """Test cron trigger stays as-is."""
        trigger = CronTrigger(expression="0 3 * * *")
        assert trigger_to_cron_expression(trigger) == "0 3 * * *"

    def test_trigger_to_cron_from_hourly(self) -> None:
        """Test hourly interval converts to cron."""
        trigger = IntervalTrigger(hours=6)
        cron = trigger_to_cron_expression(trigger)
        assert "*/6" in cron or "0" in cron

    def test_format_trigger_description_cron(self) -> None:
        """Test formatting cron trigger description."""
        trigger = CronTrigger(expression="0 3 * * *")
        desc = format_trigger_description(trigger)
        assert desc == "cron: 0 3 * * *"

    def test_format_trigger_description_interval(self) -> None:
        """Test formatting interval trigger description."""
        trigger = IntervalTrigger(hours=6)
        desc = format_trigger_description(trigger)
        assert desc == "every 6h"

    def test_get_next_run_time_interval(self) -> None:
        """Test getting next run time for interval."""
        trigger = IntervalTrigger(hours=6)
        base = datetime.now(UTC)
        next_run = get_next_run_time(trigger, base)
        assert next_run > base
        assert (next_run - base).total_seconds() == pytest.approx(6 * 3600, abs=1)

    def test_get_next_run_time_cron(self) -> None:
        """Test getting next run time for cron."""
        trigger = CronTrigger(expression="0 3 * * *")
        next_run = get_next_run_time(trigger)
        # croniter returns naive datetimes, so compare to naive now
        assert next_run > datetime.now()


# ============================================================================
# Tests for executor.py
# ============================================================================


@pytest.fixture
def mock_config() -> Config:
    """Create a mock config for testing."""
    return Config(
        radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-key"),
        sonarr=SonarrConfig(url="http://127.0.0.1:8989", api_key="sonarr-key"),
        timeout=30.0,
        tags=TagConfig(),
        scheduler=SchedulerConfig(enabled=True, history_limit=100, schedules=[]),
    )


@pytest.fixture
def mock_state_manager(tmp_path: Path) -> StateManager:
    """Create a mock state manager for testing."""
    state_path = tmp_path / "state.json"
    return StateManager(state_path)


class TestJobExecutor:
    """Tests for JobExecutor class."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_movies_schedule_success(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test executing a movies-only schedule successfully."""
        # Mock Radarr endpoints
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
                    {"id": 2, "title": "Movie 2", "year": 2024, "tags": []},
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))

        # Mock movie info and releases for each movie
        for movie_id in [1, 2]:
            respx.get(f"http://localhost:7878/api/v3/movie/{movie_id}").mock(
                return_value=Response(
                    200,
                    json={"id": movie_id, "title": f"Movie {movie_id}", "year": 2024, "tags": []},
                )
            )
            respx.get(
                "http://localhost:7878/api/v3/release", params={"movieId": str(movie_id)}
            ).mock(
                return_value=Response(
                    200,
                    json=[
                        {
                            "guid": f"rel-{movie_id}",
                            "title": f"Movie.{movie_id}.2160p.BluRay",
                            "indexer": "Test",
                            "size": 5000,
                            "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                        }
                    ],
                )
            )
            respx.post("http://localhost:7878/api/v3/tag").mock(
                return_value=Response(201, json={"id": 1, "label": "4k-available"})
            )
            respx.put(f"http://localhost:7878/api/v3/movie/{movie_id}").mock(
                return_value=Response(
                    200,
                    json={
                        "id": movie_id,
                        "title": f"Movie {movie_id}",
                        "year": 2024,
                        "tags": [1],
                    },
                )
            )

        schedule = ScheduleDefinition(
            name="test-movies",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            delay=0,  # No delay for tests
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.status == RunStatus.COMPLETED
        assert result.items_processed == 2
        assert result.items_with_4k == 2
        assert result.errors == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_with_batch_size_limit(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that batch size limits the number of items processed."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
                    {"id": 2, "title": "Movie 2", "year": 2024, "tags": []},
                    {"id": 3, "title": "Movie 3", "year": 2024, "tags": []},
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))

        # Only mock movie 1 since batch_size=1
        respx.get("http://localhost:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "1"}).mock(
            return_value=Response(200, json=[])
        )
        respx.post("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 2, "label": "4k-unavailable"})
        )
        respx.put("http://localhost:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": [2]},
            )
        )

        schedule = ScheduleDefinition(
            name="test-batch",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            batch_size=1,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.items_processed == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_series_schedule_success(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test executing a series-only schedule successfully."""
        # Mock Sonarr endpoints
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": []},
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.get("http://127.0.0.1:8989/api/v3/series/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": []},
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "1"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 1,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2024-01-01",
                        "monitored": True,
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Series.S01E01.2160p",
                        "indexer": "Test",
                        "size": 3000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.post("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-available"})
        )
        respx.put("http://127.0.0.1:8989/api/v3/series/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": [1]},
            )
        )

        schedule = ScheduleDefinition(
            name="test-series",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=6),
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.status == RunStatus.COMPLETED
        assert result.items_processed == 1
        assert result.items_with_4k == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_dry_run_no_tags(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that dry_run mode does not apply tags."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "Movie 1", "year": 2024, "tags": []}],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.get("http://localhost:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "1"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-1",
                        "title": "Movie.1.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # No tag creation/update mocks needed - dry_run shouldn't call them

        schedule = ScheduleDefinition(
            name="test-dry",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            dry_run=True,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.status == RunStatus.COMPLETED
        assert result.items_with_4k == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_skip_tagged_movies(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that skip_tagged skips already tagged movies."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Movie 1", "year": 2024, "tags": [1]},  # Already tagged
                    {"id": 2, "title": "Movie 2", "year": 2024, "tags": []},  # Not tagged
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )

        # Only mock movie 2 since movie 1 should be skipped
        respx.get("http://localhost:7878/api/v3/movie/2").mock(
            return_value=Response(
                200,
                json={"id": 2, "title": "Movie 2", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "2"}).mock(
            return_value=Response(200, json=[])
        )
        respx.put("http://localhost:7878/api/v3/movie/2").mock(
            return_value=Response(
                200,
                json={"id": 2, "title": "Movie 2", "year": 2024, "tags": [2]},
            )
        )

        schedule = ScheduleDefinition(
            name="test-skip",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            skip_tagged=True,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.items_processed == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_all_items_fail_returns_failed_status(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that when all items fail, status is FAILED."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "Movie 1", "year": 2024, "tags": []}],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.get("http://localhost:7878/api/v3/movie/1").mock(
            return_value=Response(500, json={"error": "Server error"})
        )

        schedule = ScheduleDefinition(
            name="test-error",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        # When no items are processed but there were items to process, status is FAILED
        assert result.status == RunStatus.FAILED
        assert result.items_processed == 0
        assert len(result.errors) == 1
        assert "Error checking movie 1" in result.errors[0]

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_partial_failure_returns_completed(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that when some items succeed, status is COMPLETED with errors."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
                    {"id": 2, "title": "Movie 2", "year": 2024, "tags": []},
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))

        # Movie 1 succeeds
        respx.get("http://localhost:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "1"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-1",
                        "title": "Movie.1.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.post("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-available"})
        )
        respx.put("http://localhost:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": [1]},
            )
        )

        # Movie 2 fails
        respx.get("http://localhost:7878/api/v3/movie/2").mock(
            return_value=Response(500, json={"error": "Server error"})
        )

        schedule = ScheduleDefinition(
            name="test-partial",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        # When some items are processed, status is COMPLETED
        assert result.status == RunStatus.COMPLETED
        assert result.items_processed == 1
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_execute_schedule_convenience_function(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test the execute_schedule convenience function."""
        schedule = ScheduleDefinition(
            name="test-conv",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            delay=0,
        )

        with patch.object(JobExecutor, "execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ScheduleRunRecord(
                schedule_name="test-conv",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )

            result = await execute_schedule(mock_config, mock_state_manager, schedule)

            assert result.status == RunStatus.COMPLETED
            mock_execute.assert_called_once_with(schedule)


# ============================================================================
# Tests for exporter.py
# ============================================================================


class TestExporterHelpers:
    """Tests for exporter helper functions."""

    def test_get_filtarr_path_with_which(self) -> None:
        """Test _get_filtarr_path returns which result if available."""
        with patch("shutil.which", return_value="/usr/bin/filtarr"):
            assert _get_filtarr_path() == "/usr/bin/filtarr"

    def test_get_filtarr_path_fallback(self) -> None:
        """Test _get_filtarr_path returns 'filtarr' if not found."""
        with patch("shutil.which", return_value=None):
            assert _get_filtarr_path() == "filtarr"

    def test_schedule_to_batch_args_movies(self) -> None:
        """Test converting movies schedule to batch args."""
        schedule = ScheduleDefinition(
            name="test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        args = _schedule_to_batch_args(schedule)
        assert "--all-movies" in args
        assert "--all-series" not in args

    def test_schedule_to_batch_args_series(self) -> None:
        """Test converting series schedule to batch args."""
        schedule = ScheduleDefinition(
            name="test",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=6),
        )
        args = _schedule_to_batch_args(schedule)
        assert "--all-series" in args
        assert "--all-movies" not in args

    def test_schedule_to_batch_args_both(self) -> None:
        """Test converting both schedule to batch args."""
        schedule = ScheduleDefinition(
            name="test",
            target=ScheduleTarget.BOTH,
            trigger=IntervalTrigger(hours=6),
        )
        args = _schedule_to_batch_args(schedule)
        assert "--all-movies" in args
        assert "--all-series" in args

    def test_schedule_to_batch_args_with_options(self) -> None:
        """Test converting schedule with various options."""
        schedule = ScheduleDefinition(
            name="test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            batch_size=50,
            delay=1.0,
            skip_tagged=False,
            include_rechecks=False,
            no_tag=True,
        )
        args = _schedule_to_batch_args(schedule)
        assert "--batch-size 50" in args
        assert "--delay 1.0" in args
        assert "--no-skip-tagged" in args
        assert "--no-include-rechecks" in args
        assert "--no-tag" in args

    def test_schedule_to_batch_args_series_options(self) -> None:
        """Test converting series schedule with strategy."""
        schedule = ScheduleDefinition(
            name="test",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=6),
            strategy=SeriesStrategy.DISTRIBUTED,
            seasons=5,
        )
        args = _schedule_to_batch_args(schedule)
        assert "--strategy distributed" in args
        assert "--seasons 5" in args


class TestTriggerToSystemdCalendar:
    """Tests for _trigger_to_systemd_calendar function."""

    def test_cron_trigger_conversion(self) -> None:
        """Test converting cron trigger to systemd calendar."""
        trigger = CronTrigger(expression="0 3 * * *")
        calendar = _trigger_to_systemd_calendar(trigger)
        assert "3:0:00" in calendar or "03:00:00" in calendar or "3:00:00" in calendar

    def test_cron_trigger_with_weekday(self) -> None:
        """Test converting cron with weekday to systemd calendar."""
        trigger = CronTrigger(expression="0 3 * * 1")
        calendar = _trigger_to_systemd_calendar(trigger)
        assert "Mon" in calendar

    def test_interval_trigger_minutes(self) -> None:
        """Test converting minute interval to systemd calendar."""
        trigger = IntervalTrigger(minutes=30)
        calendar = _trigger_to_systemd_calendar(trigger)
        assert "00/30" in calendar

    def test_interval_trigger_hours(self) -> None:
        """Test converting hourly interval to systemd calendar."""
        trigger = IntervalTrigger(hours=6)
        calendar = _trigger_to_systemd_calendar(trigger)
        assert "00/6" in calendar

    def test_interval_trigger_days(self) -> None:
        """Test converting daily interval to systemd calendar."""
        trigger = IntervalTrigger(days=2)
        calendar = _trigger_to_systemd_calendar(trigger)
        assert "01/2" in calendar

    def test_interval_trigger_weekly(self) -> None:
        """Test converting weekly interval to systemd calendar."""
        trigger = IntervalTrigger(weeks=1)
        calendar = _trigger_to_systemd_calendar(trigger)
        assert "Sun" in calendar


class TestExportCron:
    """Tests for export_cron function."""

    def test_export_cron_with_schedules(self) -> None:
        """Test exporting schedules to cron format."""
        schedules = [
            ScheduleDefinition(
                name="daily-movies",
                target=ScheduleTarget.MOVIES,
                trigger=CronTrigger(expression="0 3 * * *"),
                enabled=True,
            ),
        ]

        result = export_cron(schedules, filtarr_path="/usr/bin/filtarr")

        assert "# Schedule: daily-movies" in result
        assert "# Target: movies" in result
        assert "0 3 * * *" in result
        assert "/usr/bin/filtarr check batch" in result

    def test_export_cron_no_enabled_schedules(self) -> None:
        """Test exporting when no enabled schedules exist."""
        schedules = [
            ScheduleDefinition(
                name="disabled",
                target=ScheduleTarget.MOVIES,
                trigger=IntervalTrigger(hours=6),
                enabled=False,
            ),
        ]

        result = export_cron(schedules)

        assert "# No enabled schedules found" in result

    def test_export_cron_empty_list(self) -> None:
        """Test exporting empty schedule list."""
        result = export_cron([])
        assert "# No enabled schedules found" in result


class TestExportSystemdTimer:
    """Tests for export_systemd_timer function."""

    def test_export_systemd_timer_creates_both_files(self) -> None:
        """Test that export_systemd_timer returns timer and service content."""
        schedule = ScheduleDefinition(
            name="daily-check",
            target=ScheduleTarget.MOVIES,
            trigger=CronTrigger(expression="0 3 * * *"),
        )

        timer_content, service_content = export_systemd_timer(schedule, "/usr/bin/filtarr")

        # Check timer content
        assert "[Unit]" in timer_content
        assert "[Timer]" in timer_content
        assert "OnCalendar=" in timer_content
        assert "filtarr-daily-check.timer" in timer_content

        # Check service content
        assert "[Service]" in service_content
        assert "ExecStart=/usr/bin/filtarr check batch" in service_content
        assert "filtarr-daily-check.service" in service_content


class TestExportSystemd:
    """Tests for export_systemd function."""

    def test_export_systemd_returns_tuples(self) -> None:
        """Test that export_systemd returns list of tuples."""
        schedules = [
            ScheduleDefinition(
                name="test-schedule",
                target=ScheduleTarget.MOVIES,
                trigger=IntervalTrigger(hours=6),
                enabled=True,
            ),
        ]

        results = export_systemd(schedules)

        assert len(results) == 1
        name, timer, service = results[0]
        assert name == "test-schedule"
        assert "[Timer]" in timer
        assert "[Service]" in service

    def test_export_systemd_writes_files(self, tmp_path: Path) -> None:
        """Test that export_systemd writes files when output_dir is provided."""
        schedules = [
            ScheduleDefinition(
                name="test-schedule",
                target=ScheduleTarget.MOVIES,
                trigger=IntervalTrigger(hours=6),
                enabled=True,
            ),
        ]

        export_systemd(schedules, output_dir=tmp_path)

        timer_path = tmp_path / "filtarr-test-schedule.timer"
        service_path = tmp_path / "filtarr-test-schedule.service"

        assert timer_path.exists()
        assert service_path.exists()

    def test_export_systemd_skips_disabled(self) -> None:
        """Test that disabled schedules are skipped."""
        schedules = [
            ScheduleDefinition(
                name="disabled",
                target=ScheduleTarget.MOVIES,
                trigger=IntervalTrigger(hours=6),
                enabled=False,
            ),
            ScheduleDefinition(
                name="enabled",
                target=ScheduleTarget.MOVIES,
                trigger=IntervalTrigger(hours=6),
                enabled=True,
            ),
        ]

        results = export_systemd(schedules)

        assert len(results) == 1
        assert results[0][0] == "enabled"


# ============================================================================
# Tests for manager.py
# ============================================================================


class TestManagerHelpers:
    """Tests for manager helper functions."""

    def test_to_int_with_int(self) -> None:
        """Test _to_int with int value."""
        assert _to_int(42) == 42

    def test_to_int_with_float(self) -> None:
        """Test _to_int with float value."""
        assert _to_int(42.7) == 42

    def test_to_int_with_string(self) -> None:
        """Test _to_int with string value."""
        assert _to_int("42") == 42

    def test_to_int_with_invalid_string(self) -> None:
        """Test _to_int with invalid string."""
        assert _to_int("invalid", default=10) == 10

    def test_to_int_with_none(self) -> None:
        """Test _to_int with None value."""
        assert _to_int(None, default=5) == 5

    def test_to_float_with_float(self) -> None:
        """Test _to_float with float value."""
        assert _to_float(3.14) == 3.14

    def test_to_float_with_int(self) -> None:
        """Test _to_float with int value."""
        assert _to_float(42) == 42.0

    def test_to_float_with_string(self) -> None:
        """Test _to_float with string value."""
        assert _to_float("3.14") == 3.14

    def test_to_float_with_invalid_string(self) -> None:
        """Test _to_float with invalid string."""
        assert _to_float("invalid", default=1.5) == 1.5

    def test_to_float_with_none(self) -> None:
        """Test _to_float with None value."""
        assert _to_float(None, default=2.5) == 2.5


class TestSchedulerManager:
    """Tests for SchedulerManager class."""

    def test_is_running_initially_false(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that is_running is False initially."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        assert manager.is_running is False

    def test_get_all_schedules_from_config(self, mock_state_manager: StateManager) -> None:
        """Test getting schedules from config."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "test-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)
        schedules = manager.get_all_schedules()

        assert len(schedules) == 1
        assert schedules[0].name == "test-schedule"
        assert schedules[0].source == "config"

    def test_get_all_schedules_from_state(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test getting schedules from state (dynamic schedules)."""
        # Add a dynamic schedule to state
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "dynamic-schedule",
                "target": "series",
                "trigger": {"type": "interval", "hours": 12},
            }
        )

        manager = SchedulerManager(mock_config, mock_state_manager)
        schedules = manager.get_all_schedules()

        # Find the dynamic schedule
        dynamic = [s for s in schedules if s.name == "dynamic-schedule"]
        assert len(dynamic) == 1
        assert dynamic[0].source == "dynamic"

    def test_get_schedule_by_name(self, mock_state_manager: StateManager) -> None:
        """Test getting a specific schedule by name."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "my-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)
        schedule = manager.get_schedule("my-schedule")

        assert schedule is not None
        assert schedule.name == "my-schedule"

    def test_get_schedule_not_found(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test getting a non-existent schedule returns None."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        schedule = manager.get_schedule("nonexistent")
        assert schedule is None

    def test_add_schedule(self, mock_config: Config, mock_state_manager: StateManager) -> None:
        """Test adding a dynamic schedule."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        schedule = ScheduleDefinition(
            name="new-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )

        manager.add_schedule(schedule)

        # Verify it was added
        found = manager.get_schedule("new-schedule")
        assert found is not None

    def test_add_schedule_conflict_with_config(self, mock_state_manager: StateManager) -> None:
        """Test that adding a schedule with same name as config raises error."""
        config = Config(
            scheduler=SchedulerConfig(
                schedules=[
                    {
                        "name": "existing",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ]
            )
        )

        manager = SchedulerManager(config, mock_state_manager)

        schedule = ScheduleDefinition(
            name="existing",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=12),
        )

        with pytest.raises(ValueError, match=r"defined in config\.toml"):
            manager.add_schedule(schedule)

    def test_remove_schedule(self, mock_config: Config, mock_state_manager: StateManager) -> None:
        """Test removing a dynamic schedule."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Add then remove
        schedule = ScheduleDefinition(
            name="to-remove",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        manager.add_schedule(schedule)
        removed = manager.remove_schedule("to-remove")

        assert removed is True
        assert manager.get_schedule("to-remove") is None

    def test_remove_schedule_not_found(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test removing non-existent schedule returns False."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        removed = manager.remove_schedule("nonexistent")
        assert removed is False

    def test_remove_config_schedule_raises(self, mock_state_manager: StateManager) -> None:
        """Test that removing a config schedule raises ValueError."""
        config = Config(
            scheduler=SchedulerConfig(
                schedules=[
                    {
                        "name": "config-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ]
            )
        )

        manager = SchedulerManager(config, mock_state_manager)

        with pytest.raises(ValueError, match=r"defined in config\.toml"):
            manager.remove_schedule("config-schedule")

    def test_enable_schedule(self, mock_config: Config, mock_state_manager: StateManager) -> None:
        """Test enabling a dynamic schedule."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Add disabled schedule
        schedule = ScheduleDefinition(
            name="disabled-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            enabled=False,
        )
        manager.add_schedule(schedule)

        # Enable it
        result = manager.enable_schedule("disabled-schedule")
        assert result is True

    def test_disable_schedule(self, mock_config: Config, mock_state_manager: StateManager) -> None:
        """Test disabling a dynamic schedule."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Add enabled schedule
        schedule = ScheduleDefinition(
            name="enabled-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            enabled=True,
        )
        manager.add_schedule(schedule)

        # Disable it
        result = manager.disable_schedule("enabled-schedule")
        assert result is True

    def test_enable_config_schedule_raises(self, mock_state_manager: StateManager) -> None:
        """Test that enabling a config schedule raises ValueError."""
        config = Config(
            scheduler=SchedulerConfig(
                schedules=[
                    {
                        "name": "config-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                        "enabled": False,
                    }
                ]
            )
        )

        manager = SchedulerManager(config, mock_state_manager)

        with pytest.raises(ValueError, match=r"defined in config\.toml"):
            manager.enable_schedule("config-schedule")

    def test_get_running_schedules(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test getting running schedules."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        running = manager.get_running_schedules()
        assert running == set()

    def test_get_history(self, mock_config: Config, mock_state_manager: StateManager) -> None:
        """Test getting schedule history."""
        # Add some history to state
        mock_state_manager.add_schedule_run(
            {
                "schedule_name": "test",
                "started_at": datetime.now(UTC).isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "status": "completed",
                "items_processed": 10,
                "items_with_4k": 5,
                "errors": [],
            }
        )

        manager = SchedulerManager(mock_config, mock_state_manager)
        history = manager.get_history()

        assert len(history) == 1
        assert history[0].schedule_name == "test"
        assert history[0].status == RunStatus.COMPLETED

    def test_get_history_with_filter(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test getting history filtered by schedule name."""
        # Add history for two schedules
        mock_state_manager.add_schedule_run(
            {
                "schedule_name": "schedule-a",
                "started_at": datetime.now(UTC).isoformat(),
                "status": "completed",
            }
        )
        mock_state_manager.add_schedule_run(
            {
                "schedule_name": "schedule-b",
                "started_at": datetime.now(UTC).isoformat(),
                "status": "completed",
            }
        )

        manager = SchedulerManager(mock_config, mock_state_manager)
        history = manager.get_history(schedule_name="schedule-a")

        assert len(history) == 1
        assert history[0].schedule_name == "schedule-a"

    @pytest.mark.asyncio
    async def test_run_schedule_not_found(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test running a non-existent schedule raises ValueError."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        with pytest.raises(ValueError, match="Schedule not found"):
            await manager.run_schedule("nonexistent")

    @pytest.mark.asyncio
    async def test_start_no_enabled_schedules(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that start returns early with no enabled schedules."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        await manager.start()

        # Should not be running since no schedules
        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_started(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that stop is safe when not started."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        await manager.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_execute_schedule_overlap_protection(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that overlapping schedule runs are skipped."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        schedule = ScheduleDefinition(
            name="overlap-test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )

        # Simulate a running job
        manager._running_jobs.add("overlap-test")

        result = await manager._execute_schedule(schedule)

        assert result.status == RunStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_job_callback_schedule_not_found(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that job callback handles missing schedule gracefully."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Should not raise, just log
        await manager._job_callback("nonexistent")

    @pytest.mark.asyncio
    async def test_start_already_started_warns(self, mock_state_manager: StateManager) -> None:
        """Test that starting an already started scheduler logs warning."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "test",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)
        manager._started = True

        # Should return early without error
        await manager.start()
