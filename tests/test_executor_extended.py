"""Extended tests for scheduler/executor.py edge cases."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from filtarr.config import Config, RadarrConfig, SchedulerConfig, SonarrConfig, TagConfig
from filtarr.scheduler import (
    IntervalTrigger,
    RunStatus,
    ScheduleDefinition,
    ScheduleTarget,
    SeriesStrategy,
)
from filtarr.scheduler.executor import JobExecutor
from filtarr.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def mock_config() -> Config:
    """Create a mock config for testing."""
    return Config(
        radarr=RadarrConfig(url="http://radarr:7878", api_key="radarr-key"),
        sonarr=SonarrConfig(url="http://sonarr:8989", api_key="sonarr-key"),
        timeout=30.0,
        tags=TagConfig(),
        scheduler=SchedulerConfig(enabled=True, history_limit=100, schedules=[]),
    )


@pytest.fixture
def mock_state_manager(tmp_path: Path) -> StateManager:
    """Create a mock state manager for testing."""
    state_path = tmp_path / "state.json"
    return StateManager(state_path)


class TestExecutorSeriesBatchLimit:
    """Tests for batch size limit during series processing."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_batch_limit_reached_during_series(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Batch size limit should stop processing when reached during series checks."""
        # Mock movies - process 1
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "Movie 1", "year": 2024, "tags": []}],
            )
        )
        respx.get("http://radarr:7878/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.get("http://radarr:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "1"}).mock(
            return_value=Response(200, json=[])
        )
        respx.post("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-unavailable"})
        )
        respx.put("http://radarr:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": [1]},
            )
        )

        # Mock series - would process 2 but batch limit is 2 total
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": []},
                    {"id": 2, "title": "Series 2", "year": 2024, "seasons": [], "tags": []},
                ],
            )
        )
        respx.get("http://sonarr:8989/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.get("http://sonarr:8989/api/v3/series/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": []},
            )
        )
        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "1"}).mock(
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
        respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(200, json=[])
        )
        respx.post("http://sonarr:8989/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-unavailable"})
        )
        respx.put("http://sonarr:8989/api/v3/series/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": [1]},
            )
        )
        # Series 2 should not be called since batch limit is 2

        schedule = ScheduleDefinition(
            name="test-batch-limit",
            target=ScheduleTarget.BOTH,
            trigger=IntervalTrigger(hours=6),
            batch_size=2,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        # Should have processed exactly 2 items: 1 movie + 1 series
        assert result.items_processed == 2
        assert result.status == RunStatus.COMPLETED


class TestExecutorSeriesCheckErrors:
    """Tests for exception handling during series checks."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_series_check_error_continues_processing(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Series check errors should be caught and logged, not stop processing."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": []},
                    {"id": 2, "title": "Series 2", "year": 2024, "seasons": [], "tags": []},
                ],
            )
        )
        respx.get("http://sonarr:8989/api/v3/tag").mock(return_value=Response(200, json=[]))

        # Series 1 fails
        respx.get("http://sonarr:8989/api/v3/series/1").mock(
            return_value=Response(500, json={"error": "Server error"})
        )

        # Series 2 succeeds
        respx.get("http://sonarr:8989/api/v3/series/2").mock(
            return_value=Response(
                200,
                json={"id": 2, "title": "Series 2", "year": 2024, "seasons": [], "tags": []},
            )
        )
        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "2"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 201,
                        "seriesId": 2,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2024-01-01",
                        "monitored": True,
                    }
                ],
            )
        )
        respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": "201"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-201",
                        "title": "Series.S01E01.2160p",
                        "indexer": "Test",
                        "size": 3000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.post("http://sonarr:8989/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-available"})
        )
        respx.put("http://sonarr:8989/api/v3/series/2").mock(
            return_value=Response(
                200,
                json={"id": 2, "title": "Series 2", "year": 2024, "seasons": [], "tags": [1]},
            )
        )

        schedule = ScheduleDefinition(
            name="test-series-error",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=6),
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        # One success, one error
        assert result.items_processed == 1
        assert result.items_with_4k == 1
        assert len(result.errors) == 1
        assert "Error checking series 1" in result.errors[0]
        assert result.status == RunStatus.COMPLETED


class TestExecutorWithDelay:
    """Tests for delay handling between checks."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_with_delay_calls_asyncio_sleep(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Delay should trigger asyncio.sleep between items."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
                    {"id": 2, "title": "Movie 2", "year": 2024, "tags": []},
                ],
            )
        )
        respx.get("http://radarr:7878/api/v3/tag").mock(return_value=Response(200, json=[]))

        for movie_id in [1, 2]:
            respx.get(f"http://radarr:7878/api/v3/movie/{movie_id}").mock(
                return_value=Response(
                    200,
                    json={"id": movie_id, "title": f"Movie {movie_id}", "year": 2024, "tags": []},
                )
            )
            respx.get("http://radarr:7878/api/v3/release", params={"movieId": str(movie_id)}).mock(
                return_value=Response(200, json=[])
            )
            respx.post("http://radarr:7878/api/v3/tag").mock(
                return_value=Response(201, json={"id": 1, "label": "4k-unavailable"})
            )
            respx.put(f"http://radarr:7878/api/v3/movie/{movie_id}").mock(
                return_value=Response(
                    200,
                    json={"id": movie_id, "title": f"Movie {movie_id}", "year": 2024, "tags": [1]},
                )
            )

        schedule = ScheduleDefinition(
            name="test-delay",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            delay=0.5,  # 0.5 second delay
        )

        executor = JobExecutor(mock_config, mock_state_manager)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await executor.execute(schedule)

            # Should have called sleep with delay after each item
            # (delay is called after each movie, so 2 times for 2 movies)
            assert mock_sleep.call_count == 2
            mock_sleep.assert_called_with(0.5)

        assert result.items_processed == 2


class TestExecutorTopLevelException:
    """Tests for top-level exception handling in execute()."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_top_level_exception_returns_failed(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Top-level exception should result in RunStatus.FAILED."""
        # Mock get_all_movies to raise an exception
        respx.get("http://radarr:7878/api/v3/movie").mock(
            side_effect=Exception("Unexpected server error")
        )

        schedule = ScheduleDefinition(
            name="test-top-error",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.status == RunStatus.FAILED
        assert len(result.errors) == 1
        assert "Schedule execution failed" in result.errors[0]

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_both_targets_top_level_exception(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Exception during get movies/series list should fail the run."""
        # Movies call fails
        respx.get("http://radarr:7878/api/v3/movie").mock(
            side_effect=Exception("Radarr unavailable")
        )

        schedule = ScheduleDefinition(
            name="test-both-fail",
            target=ScheduleTarget.BOTH,
            trigger=IntervalTrigger(hours=6),
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.status == RunStatus.FAILED
        assert len(result.errors) >= 1


class TestGetSeriesToCheck:
    """Tests for _get_series_to_check method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_to_check_skip_tagged_false(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """skip_tagged=False should return all series."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": [1]},
                    {"id": 2, "title": "Series 2", "year": 2024, "seasons": [], "tags": []},
                ],
            )
        )

        schedule = ScheduleDefinition(
            name="test-skip-false",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=6),
            skip_tagged=False,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        series = await executor._get_series_to_check(schedule)

        # Both series should be returned since skip_tagged=False
        assert len(series) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_to_check_skip_tagged_true(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """skip_tagged=True should filter out tagged series."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Series 1", "year": 2024, "seasons": [], "tags": [1]},
                    {"id": 2, "title": "Series 2", "year": 2024, "seasons": [], "tags": []},
                ],
            )
        )
        respx.get("http://sonarr:8989/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )

        schedule = ScheduleDefinition(
            name="test-skip-true",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=6),
            skip_tagged=True,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        series = await executor._get_series_to_check(schedule)

        # Only series 2 should be returned (series 1 has tag id 1 which is 4k-available)
        assert len(series) == 1
        assert series[0].id == 2


class TestGetMoviesToCheck:
    """Tests for _get_movies_to_check method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_movies_to_check_skip_tagged_false(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """skip_tagged=False should return all movies."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Movie 1", "year": 2024, "tags": [1]},
                    {"id": 2, "title": "Movie 2", "year": 2024, "tags": []},
                ],
            )
        )

        schedule = ScheduleDefinition(
            name="test-movie-skip-false",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            skip_tagged=False,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        movies = await executor._get_movies_to_check(schedule)

        # Both movies should be returned
        assert len(movies) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_movies_to_check_skip_tagged_true(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """skip_tagged=True should filter out tagged movies."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Movie 1", "year": 2024, "tags": [1]},
                    {"id": 2, "title": "Movie 2", "year": 2024, "tags": [2]},
                    {"id": 3, "title": "Movie 3", "year": 2024, "tags": []},
                ],
            )
        )
        respx.get("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )

        schedule = ScheduleDefinition(
            name="test-movie-skip-true",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            skip_tagged=True,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        movies = await executor._get_movies_to_check(schedule)

        # Only movie 3 should be returned (movie 1 and 2 have skip tags)
        assert len(movies) == 1
        assert movies[0].id == 3


class TestExecutorNoTagMode:
    """Tests for no_tag mode in executor."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_no_tag_does_not_apply_tags(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """no_tag mode should not apply tags to items."""
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "Movie 1", "year": 2024, "tags": []}],
            )
        )
        respx.get("http://radarr:7878/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.get("http://radarr:7878/api/v3/movie/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "1"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # No tag operations (POST/PUT) should be mocked - they should not be called

        schedule = ScheduleDefinition(
            name="test-no-tag",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            no_tag=True,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.items_processed == 1
        assert result.items_with_4k == 1
        # Status should be completed
        assert result.status == RunStatus.COMPLETED


class TestExecutorSeriesStrategy:
    """Tests for series strategy handling in executor."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_execute_series_with_distributed_strategy(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Series check should use the strategy from schedule definition."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "title": "Long Series", "year": 2020, "seasons": [], "tags": []}],
            )
        )
        respx.get("http://sonarr:8989/api/v3/tag").mock(return_value=Response(200, json=[]))
        respx.get("http://sonarr:8989/api/v3/series/1").mock(
            return_value=Response(
                200,
                json={"id": 1, "title": "Long Series", "year": 2020, "seasons": [], "tags": []},
            )
        )
        # 5 seasons of episodes
        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "1"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 100 + i,
                        "seriesId": 1,
                        "seasonNumber": i,
                        "episodeNumber": 1,
                        "airDate": f"202{i}-01-01",
                        "monitored": True,
                    }
                    for i in range(1, 6)  # seasons 1-5
                ],
            )
        )
        # Mock releases for seasons 1, 3, 5 (distributed would pick first, middle, last)
        for ep_id in [101, 103, 105]:
            respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": str(ep_id)}).mock(
                return_value=Response(200, json=[])
            )

        respx.post("http://sonarr:8989/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-unavailable"})
        )
        respx.put("http://sonarr:8989/api/v3/series/1").mock(
            return_value=Response(
                200,
                json={
                    "id": 1,
                    "title": "Long Series",
                    "year": 2020,
                    "seasons": [],
                    "tags": [1],
                },
            )
        )

        schedule = ScheduleDefinition(
            name="test-distributed",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=6),
            strategy=SeriesStrategy.DISTRIBUTED,
            delay=0,
        )

        executor = JobExecutor(mock_config, mock_state_manager)
        result = await executor.execute(schedule)

        assert result.items_processed == 1
        assert result.status == RunStatus.COMPLETED
