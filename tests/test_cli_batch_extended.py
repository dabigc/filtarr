"""Extended tests for CLI batch processing edge cases."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from httpx import Response
from rich.console import Console
from typer.testing import CliRunner

from filtarr.checker import ReleaseChecker, SamplingStrategy, SearchResult
from filtarr.cli import (
    BatchContext,
    OutputFormat,
    _build_item_list,
    _fetch_movies_to_check,
    _fetch_series_to_check,
    _handle_batch_result,
    _process_batch_item,
    _process_movie_item,
    _process_series_item,
    _process_single_item,
    _run_batch_checks,
    app,
)
from filtarr.config import Config, ConfigurationError, RadarrConfig, SonarrConfig, TagConfig
from filtarr.criteria import SearchCriteria
from filtarr.state import BatchProgress, StateManager
from filtarr.tagger import TagResult

if TYPE_CHECKING:
    from filtarr.models.radarr import Movie
    from filtarr.models.sonarr import Series

runner = CliRunner()


@pytest.fixture
def mock_config() -> Config:
    """Create a mock config for testing."""
    return Config(
        radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-key"),
        sonarr=SonarrConfig(url="http://127.0.0.1:8989", api_key="sonarr-key"),
        timeout=30.0,
        tags=TagConfig(),
    )


@pytest.fixture
def mock_console() -> Any:
    """Create a mock console for testing."""
    console = MagicMock(spec=Console)
    console.print = MagicMock()
    return console


@pytest.fixture
def mock_error_console() -> Any:
    """Create a mock error console for testing."""
    console = MagicMock(spec=Console)
    console.print = MagicMock()
    return console


@pytest.fixture
def mock_state_manager() -> MagicMock:
    """Create a mock StateManager for testing."""
    mock = MagicMock(spec=StateManager)
    mock.record_check = MagicMock()
    mock.update_batch_progress = MagicMock()
    mock.start_batch = MagicMock()
    mock.get_batch_progress = MagicMock(return_value=None)
    mock.clear_batch_progress = MagicMock()
    mock.get_stale_unavailable_items = MagicMock(return_value=[])
    mock.get_cached_result = MagicMock(return_value=None)
    return mock


@pytest.fixture
def real_console() -> Console:
    """Create a real Console for tests that require it (Progress bar)."""
    return Console(file=StringIO(), force_terminal=True)


class TestFetchMoviesToCheck:
    """Tests for _fetch_movies_to_check function."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_movies_skip_tagged_true_filters_movies(
        self, mock_config: Config, mock_console: Any
    ) -> None:
        """skip_tagged=True should filter out movies with matching tags."""
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Tagged Movie", "year": 2024, "tags": [1]},
                    {"id": 2, "title": "Untagged Movie", "year": 2024, "tags": []},
                    {"id": 3, "title": "Other Tagged Movie", "year": 2024, "tags": [2]},
                ],
            )
        )

        movies, skip_tags = await _fetch_movies_to_check(
            mock_config, SearchCriteria.FOUR_K, skip_tagged=True, console=mock_console
        )

        # Only movie 2 should be in the result (movies 1 and 3 have skip tags)
        assert len(movies) == 1
        assert movies[0].id == 2
        assert skip_tags == {1, 2}

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_movies_skip_tagged_false_returns_all(
        self, mock_config: Config, mock_console: Any
    ) -> None:
        """skip_tagged=False should return all movies."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Tagged Movie", "year": 2024, "tags": [1]},
                    {"id": 2, "title": "Untagged Movie", "year": 2024, "tags": []},
                ],
            )
        )

        movies, skip_tags = await _fetch_movies_to_check(
            mock_config, SearchCriteria.FOUR_K, skip_tagged=False, console=mock_console
        )

        # All movies should be returned
        assert len(movies) == 2
        assert skip_tags == set()

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_movies_with_different_criteria_tag_names(
        self, mock_config: Config, mock_console: Any
    ) -> None:
        """Different criteria should use different tag names for filtering."""
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "hdr-available"},
                    {"id": 3, "label": "hdr-unavailable"},
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "4K Movie", "year": 2024, "tags": [1]},  # Has 4k tag
                    {"id": 2, "title": "HDR Movie", "year": 2024, "tags": [2]},  # Has hdr tag
                    {"id": 3, "title": "Fresh Movie", "year": 2024, "tags": []},
                ],
            )
        )

        # Search for HDR - should skip movie 2 (has hdr tag) but include movie 1
        movies, skip_tags = await _fetch_movies_to_check(
            mock_config, SearchCriteria.HDR, skip_tagged=True, console=mock_console
        )

        assert len(movies) == 2  # Movies 1 and 3 (movie 2 has hdr tag)
        assert skip_tags == {2, 3}


class TestFetchSeriesToCheck:
    """Tests for _fetch_series_to_check function."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_series_skip_tagged_true_filters_series(
        self, mock_config: Config, mock_console: Any
    ) -> None:
        """skip_tagged=True should filter out series with matching tags."""
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Tagged Series", "year": 2024, "seasons": [], "tags": [1]},
                    {"id": 2, "title": "Untagged Series", "year": 2024, "seasons": [], "tags": []},
                ],
            )
        )

        series, skip_tags = await _fetch_series_to_check(
            mock_config, SearchCriteria.FOUR_K, skip_tagged=True, console=mock_console
        )

        # Only series 2 should be in result
        assert len(series) == 1
        assert series[0].id == 2
        assert skip_tags == {1, 2}

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_series_skip_tagged_false_returns_all(
        self, mock_config: Config, mock_console: Any
    ) -> None:
        """skip_tagged=False should return all series."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Tagged Series", "year": 2024, "seasons": [], "tags": [1]},
                    {"id": 2, "title": "Untagged Series", "year": 2024, "seasons": [], "tags": []},
                ],
            )
        )

        series, skip_tags = await _fetch_series_to_check(
            mock_config, SearchCriteria.FOUR_K, skip_tagged=False, console=mock_console
        )

        # All series should be returned
        assert len(series) == 2
        assert skip_tags == set()


class TestProcessMovieItem:
    """Tests for _process_movie_item function."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_movie_by_name_no_matches(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Movie lookup by name with no matches should return None."""
        respx.get("http://localhost:7878/api/v3/movie").mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        result = await _process_movie_item(
            checker=checker,
            item_id=-1,  # Negative means lookup by name
            item_name="Nonexistent Movie",
            search_criteria=SearchCriteria.FOUR_K,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is None
        mock_error_console.print.assert_called()
        # Check that error was printed
        call_args = str(mock_error_console.print.call_args)
        assert "Movie not found" in call_args or "not found" in call_args.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_movie_by_name_multiple_matches(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Movie lookup by name with multiple matches should return None."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003},
                    {"id": 3, "title": "The Matrix Revolutions", "year": 2003},
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        result = await _process_movie_item(
            checker=checker,
            item_id=-1,
            item_name="The Matrix",
            search_criteria=SearchCriteria.FOUR_K,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is None
        mock_error_console.print.assert_called()
        call_args = str(mock_error_console.print.call_args)
        assert "Multiple movies" in call_args or "multiple" in call_args.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_movie_by_id_success(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Movie lookup by ID should check the movie directly."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
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

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        result = await _process_movie_item(
            checker=checker,
            item_id=123,
            item_name="Test Movie",
            search_criteria=SearchCriteria.FOUR_K,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        assert result.has_match is True
        assert result.item_id == 123

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_movie_by_name_single_match(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Movie lookup by name with single match should process the movie."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 456, "title": "Inception", "year": 2010}],
            )
        )
        # check_movie fetches movie info first
        respx.get("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Inception", "year": 2010, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(200, json=[])
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        result = await _process_movie_item(
            checker=checker,
            item_id=-1,
            item_name="Inception",
            search_criteria=SearchCriteria.FOUR_K,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        assert result.item_id == 456
        mock_console.print.assert_called()  # "Found: Inception" message


class TestProcessSeriesItem:
    """Tests for _process_series_item function."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_series_by_name_no_matches(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Series lookup by name with no matches should return None."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        result = await _process_series_item(
            checker=checker,
            item_id=-1,
            item_name="Nonexistent Series",
            series_criteria=SearchCriteria.FOUR_K,
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is None
        mock_error_console.print.assert_called()
        call_args = str(mock_error_console.print.call_args)
        assert "Series not found" in call_args or "not found" in call_args.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_series_by_name_multiple_matches(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Series lookup by name with multiple matches should return None."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []},
                    {"id": 2, "title": "Breaking Bad (2022)", "year": 2022, "seasons": []},
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        result = await _process_series_item(
            checker=checker,
            item_id=-1,
            item_name="Breaking",
            series_criteria=SearchCriteria.FOUR_K,
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is None
        mock_error_console.print.assert_called()
        call_args = str(mock_error_console.print.call_args)
        assert "Multiple series" in call_args or "multiple" in call_args.lower()

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_series_by_id_success(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Series lookup by ID should check the series directly."""
        respx.get("http://127.0.0.1:8989/api/v3/series/789").mock(
            return_value=Response(
                200,
                json={"id": 789, "title": "Test Series", "year": 2020, "seasons": [], "tags": []},
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "789"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 789,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
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
                        "title": "Series.S01E01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 3000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        result = await _process_series_item(
            checker=checker,
            item_id=789,
            item_name="Test Series",
            series_criteria=SearchCriteria.FOUR_K,
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        assert result.has_match is True
        assert result.item_id == 789

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_series_by_name_single_match(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Series lookup by name with single match should process the series."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 456, "title": "Game of Thrones", "year": 2011, "seasons": []}],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Game of Thrones", "year": 2011, "seasons": []},
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 456,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2011-04-17",
                        "monitored": True,
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "1001"}).mock(
            return_value=Response(200, json=[])
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        result = await _process_series_item(
            checker=checker,
            item_id=-1,
            item_name="Game of Thrones",
            series_criteria=SearchCriteria.FOUR_K,
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        assert result.item_id == 456
        mock_console.print.assert_called()  # "Found: Game of Thrones" message


class TestProcessMovieItemWithDifferentCriteria:
    """Tests for _process_movie_item with various criteria."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_movie_with_hdr_criteria(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Movie processing with HDR criteria should search for HDR releases."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "HDR Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.2160p.HDR.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        result = await _process_movie_item(
            checker=checker,
            item_id=123,
            item_name="HDR Movie",
            search_criteria=SearchCriteria.HDR,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        assert result.has_match is True


class TestProcessSeriesItemWithStrategies:
    """Tests for _process_series_item with different sampling strategies."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_series_with_all_strategy(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Series processing with ALL strategy should check all seasons."""
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Short Series", "year": 2023, "seasons": []},
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2023-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2023-06-01",
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(200, json=[])
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "201"}).mock(
            return_value=Response(200, json=[])
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        result = await _process_series_item(
            checker=checker,
            item_id=123,
            item_name="Short Series",
            series_criteria=SearchCriteria.FOUR_K,
            sampling_strategy=SamplingStrategy.ALL,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        # ALL strategy should check all seasons (2 in this case)
        assert len(result.seasons_checked) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_series_with_distributed_strategy(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Series processing with DISTRIBUTED strategy should check first, middle, last."""
        respx.get("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Long Series", "year": 2018, "seasons": []},
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 100 + i,
                        "seriesId": 456,
                        "seasonNumber": i,
                        "episodeNumber": 1,
                        "airDate": f"201{i}-01-01",
                        "monitored": True,
                    }
                    for i in range(1, 6)  # Seasons 1-5
                ],
            )
        )
        # Distributed should check seasons 1, 3, 5
        for ep_id in [101, 103, 105]:
            respx.get(
                "http://127.0.0.1:8989/api/v3/release", params={"episodeId": str(ep_id)}
            ).mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        result = await _process_series_item(
            checker=checker,
            item_id=456,
            item_name="Long Series",
            series_criteria=SearchCriteria.FOUR_K,
            sampling_strategy=SamplingStrategy.DISTRIBUTED,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        # DISTRIBUTED should check first, middle, last (seasons 1, 3, 5)
        assert sorted(result.seasons_checked) == [1, 3, 5]


class TestProcessItemsWithDryRun:
    """Tests for dry_run mode in item processing."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_movie_dry_run_no_tag_changes(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """dry_run mode should not apply actual tags."""
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        # No tag API mocks needed - dry_run shouldn't call them

        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=TagConfig(),
        )

        result = await _process_movie_item(
            checker=checker,
            item_id=123,
            item_name="Test Movie",
            search_criteria=SearchCriteria.FOUR_K,
            apply_tags=True,
            dry_run=True,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is not None
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.dry_run is True


class TestProcessMovieItemEdgeCases:
    """Edge case tests for _process_movie_item."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_movie_by_name_truncates_multiple_matches_display(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """When many matches are found, display should be truncated."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": i, "title": f"Movie Part {i}", "year": 2020 + i}
                    for i in range(1, 10)  # 9 movies
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        result = await _process_movie_item(
            checker=checker,
            item_id=-1,
            item_name="Movie Part",
            search_criteria=SearchCriteria.FOUR_K,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is None
        # Error console should show truncated message with "..."
        call_args = str(mock_error_console.print.call_args)
        assert "..." in call_args


class TestProcessSeriesItemEdgeCases:
    """Edge case tests for _process_series_item."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_process_series_by_name_truncates_multiple_matches_display(
        self, mock_console: Any, mock_error_console: Any
    ) -> None:
        """When many series matches are found, display should be truncated."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": i, "title": f"Series Season {i}", "year": 2020 + i, "seasons": []}
                    for i in range(1, 10)  # 9 series
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        result = await _process_series_item(
            checker=checker,
            item_id=-1,
            item_name="Series Season",
            series_criteria=SearchCriteria.FOUR_K,
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            console=mock_console,
            error_console=mock_error_console,
        )

        assert result is None
        # Error console should show truncated message with "..."
        call_args = str(mock_error_console.print.call_args)
        assert "..." in call_args


# =============================================================================
# NEW TESTS FOR UNCOVERED LINES
# =============================================================================


class TestMovieOnlyCriteriaWarningForSeries:
    """Tests for L825-829: Movie-only criteria warning for series in batch processing."""

    @pytest.mark.asyncio
    async def test_process_batch_item_with_directors_cut_on_series(
        self, mock_config: Config, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Should warn and fallback to 4K when directors-cut is used for series."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=MagicMock(spec=StateManager),
            search_criteria=SearchCriteria.DIRECTORS_CUT,
            criteria_str="directors-cut",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # Mock the get_checker to return an async mock checker
        mock_checker = AsyncMock()
        mock_checker.check_series.return_value = SearchResult(
            item_id=456, item_type="series", has_match=False
        )

        with patch("filtarr.cli.get_checker", return_value=mock_checker):
            await _process_batch_item(ctx, "series", 456, "Test Series")

        # Should have printed the warning about movie-only criteria
        warning_printed = any(
            "directors-cut" in str(call).lower() and "movie-only" in str(call).lower()
            for call in mock_console.print.call_args_list
        )
        assert warning_printed or any(
            "Using 4K" in str(call) for call in mock_console.print.call_args_list
        )

    @pytest.mark.asyncio
    async def test_process_batch_item_with_extended_on_series(
        self, mock_config: Config, mock_console: Any, mock_error_console: Any
    ) -> None:
        """Should warn and fallback to 4K when extended is used for series."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=MagicMock(spec=StateManager),
            search_criteria=SearchCriteria.EXTENDED,
            criteria_str="extended",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        mock_checker = AsyncMock()
        mock_checker.check_series.return_value = SearchResult(
            item_id=456, item_type="series", has_match=False
        )

        with patch("filtarr.cli.get_checker", return_value=mock_checker):
            await _process_batch_item(ctx, "series", 456, "Test Series")

        # Check that warning about movie-only criteria was printed
        assert mock_console.print.called
        call_args_str = " ".join(str(call) for call in mock_console.print.call_args_list)
        assert "4K" in call_args_str or "movie-only" in call_args_str.lower()


class TestHandleBatchResult:
    """Tests for L857, L866: State recording and batch progress update."""

    def test_handle_batch_result_records_state_when_not_dry_run_with_tags(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should record check in state when dry_run=False and apply_tags=True."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=True,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # Create a result with tag_result
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            tag_result=TagResult(tag_applied="4k-available"),
        )

        batch_progress = BatchProgress(batch_id="test-batch", item_type="movie", total_items=10)

        _handle_batch_result(ctx, result, item_id=123, batch_progress=batch_progress)

        # Should have recorded the check
        mock_state_manager.record_check.assert_called_once_with("movie", 123, True, "4k-available")
        # Should have updated batch progress
        mock_state_manager.update_batch_progress.assert_called_once_with(123)

    def test_handle_batch_result_updates_progress_with_valid_item_id(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should update batch progress when item_id > 0."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=True,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        result = SearchResult(item_id=456, item_type="movie", has_match=False)
        batch_progress = BatchProgress(batch_id="test-batch", item_type="movie", total_items=10)

        _handle_batch_result(ctx, result, item_id=456, batch_progress=batch_progress)

        # Should have updated batch progress (even in dry_run)
        mock_state_manager.update_batch_progress.assert_called_once_with(456)

    def test_handle_batch_result_no_update_for_negative_item_id(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should not update batch progress when item_id <= 0."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        result = SearchResult(item_id=123, item_type="movie", has_match=False)
        batch_progress = BatchProgress(batch_id="test-batch", item_type="movie", total_items=10)

        _handle_batch_result(ctx, result, item_id=-1, batch_progress=batch_progress)

        # Should NOT have updated batch progress for negative item_id
        mock_state_manager.update_batch_progress.assert_not_called()


class TestBuildItemList:
    """Tests for L880, L883: Movie/series append in _build_item_list()."""

    def test_build_item_list_with_movies(self) -> None:
        """Should add movies to all_items list."""
        # Create mock Movie objects
        mock_movie1 = MagicMock()
        mock_movie1.id = 1
        mock_movie1.title = "Movie 1"

        mock_movie2 = MagicMock()
        mock_movie2.id = 2
        mock_movie2.title = "Movie 2"

        movies: list[Movie] = [mock_movie1, mock_movie2]
        series: list[Series] = []
        file_items: list[tuple[str, str]] = []

        result = _build_item_list(movies, series, file_items)

        assert len(result) == 2
        assert result[0] == ("movie", 1, "Movie 1")
        assert result[1] == ("movie", 2, "Movie 2")

    def test_build_item_list_with_series(self) -> None:
        """Should add series to all_items list."""
        mock_series1 = MagicMock()
        mock_series1.id = 100
        mock_series1.title = "Series 1"

        mock_series2 = MagicMock()
        mock_series2.id = 200
        mock_series2.title = "Series 2"

        movies: list[Movie] = []
        series: list[Series] = [mock_series1, mock_series2]
        file_items: list[tuple[str, str]] = []

        result = _build_item_list(movies, series, file_items)

        assert len(result) == 2
        assert result[0] == ("series", 100, "Series 1")
        assert result[1] == ("series", 200, "Series 2")

    def test_build_item_list_with_mixed_items(self) -> None:
        """Should add movies, series, and file items correctly."""
        mock_movie = MagicMock()
        mock_movie.id = 1
        mock_movie.title = "Test Movie"

        mock_series = MagicMock()
        mock_series.id = 100
        mock_series.title = "Test Series"

        movies: list[Movie] = [mock_movie]
        series: list[Series] = [mock_series]
        file_items: list[tuple[str, str]] = [
            ("movie", "456"),
            ("series", "Breaking Bad"),
        ]

        result = _build_item_list(movies, series, file_items)

        assert len(result) == 4
        assert result[0] == ("movie", 1, "Test Movie")
        assert result[1] == ("series", 100, "Test Series")
        assert result[2] == ("movie", 456, "ID:456")
        assert result[3] == ("series", -1, "Breaking Bad")


class TestProcessSingleItemErrorHandlers:
    """Tests for L945-962: Batch error handlers in _process_single_item()."""

    @pytest.mark.asyncio
    async def test_batch_limit_reached_returns_false(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should return False and set batch_limit_reached when batch_size > 0 and limit reached."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=1,  # Limit of 1
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        mock_result = SearchResult(item_id=123, item_type="movie", has_match=True)

        with patch("filtarr.cli._process_batch_item", return_value=mock_result):
            should_continue = await _process_single_item(
                ctx, "movie", 123, "Test Movie", batch_progress=None
            )

        # First item should be processed (processed_this_run=1), then limit reached
        assert ctx.processed_this_run == 1
        assert ctx.batch_limit_reached is True
        assert should_continue is False

    @pytest.mark.asyncio
    async def test_configuration_error_handling(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should handle ConfigurationError and mark as processed."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        batch_progress = BatchProgress(batch_id="test", item_type="movie", total_items=10)

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=ConfigurationError("Radarr not configured"),
        ):
            should_continue = await _process_single_item(
                ctx, "movie", 123, "Test Movie", batch_progress=batch_progress
            )

        # Should print error and mark as processed
        assert should_continue is True
        mock_error_console.print.assert_called()
        mock_state_manager.update_batch_progress.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_http_status_error_transient_not_marked_processed(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should NOT mark as processed for transient HTTP errors (5xx)."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        batch_progress = BatchProgress(batch_id="test", item_type="movie", total_items=10)

        mock_response = MagicMock()
        mock_response.status_code = 502  # Bad Gateway - transient
        mock_request = MagicMock()

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=httpx.HTTPStatusError(
                "Bad Gateway", request=mock_request, response=mock_response
            ),
        ):
            should_continue = await _process_single_item(
                ctx, "movie", 123, "Test Movie", batch_progress=batch_progress
            )

        # Should print error but NOT mark as processed for transient error
        assert should_continue is True
        mock_error_console.print.assert_called()
        mock_state_manager.update_batch_progress.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_status_error_non_transient_marked_processed(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should mark as processed for non-transient HTTP errors (4xx)."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        batch_progress = BatchProgress(batch_id="test", item_type="movie", total_items=10)

        mock_response = MagicMock()
        mock_response.status_code = 404  # Not Found - permanent
        mock_request = MagicMock()

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=mock_request, response=mock_response
            ),
        ):
            should_continue = await _process_single_item(
                ctx, "movie", 123, "Test Movie", batch_progress=batch_progress
            )

        # Should print error and mark as processed
        assert should_continue is True
        mock_error_console.print.assert_called()
        mock_state_manager.update_batch_progress.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_network_error_not_marked_processed(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should NOT mark as processed for network errors (transient)."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        batch_progress = BatchProgress(batch_id="test", item_type="movie", total_items=10)

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            should_continue = await _process_single_item(
                ctx, "movie", 123, "Test Movie", batch_progress=batch_progress
            )

        # Should print error but NOT mark as processed
        assert should_continue is True
        mock_error_console.print.assert_called()
        mock_state_manager.update_batch_progress.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_exception_not_marked_processed(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should NOT mark as processed for timeout exceptions."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        batch_progress = BatchProgress(batch_id="test", item_type="movie", total_items=10)

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=httpx.TimeoutException("Request timed out"),
        ):
            should_continue = await _process_single_item(
                ctx, "movie", 123, "Test Movie", batch_progress=batch_progress
            )

        # Should print error but NOT mark as processed
        assert should_continue is True
        mock_error_console.print.assert_called()
        mock_state_manager.update_batch_progress.assert_not_called()

    @pytest.mark.asyncio
    async def test_general_exception_not_marked_processed(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should NOT mark as processed for general exceptions."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        batch_progress = BatchProgress(batch_id="test", item_type="movie", total_items=10)

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=RuntimeError("Unknown error"),
        ):
            should_continue = await _process_single_item(
                ctx, "movie", 123, "Test Movie", batch_progress=batch_progress
            )

        # Should print error but NOT mark as processed
        assert should_continue is True
        mock_error_console.print.assert_called()
        mock_state_manager.update_batch_progress.assert_not_called()


class TestBatchProgressHandling:
    """Tests for L1002-1006: Existing batch progress handling and L1024-1026: Skip processed items."""

    def test_batch_command_uses_existing_progress_on_resume(self) -> None:
        """Should use existing batch progress when resume=True."""
        existing_progress = BatchProgress(
            batch_id="existing-batch",
            item_type="movie",
            total_items=10,
            processed_ids={1, 2, 3},
        )

        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = MagicMock(spec=StateManager)
        mock_state_manager.get_batch_progress.return_value = existing_progress
        mock_state_manager.get_stale_unavailable_items.return_value = []

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli._fetch_movies_to_check") as mock_fetch,
        ):
            mock_movie = MagicMock()
            mock_movie.id = 1
            mock_movie.title = "Already Processed Movie"
            mock_fetch.return_value = ([mock_movie], set())

            result = runner.invoke(
                app,
                ["check", "batch", "--all-movies", "--format", "simple"],
            )

        # Should have printed resuming message
        assert "Resuming batch" in result.output or "already processed" in result.output.lower()

    def test_batch_skips_processed_items_in_resume_mode(self) -> None:
        """Should skip items that are already processed in resume mode."""
        existing_progress = BatchProgress(
            batch_id="existing-batch",
            item_type="movie",
            total_items=3,
            processed_ids={1, 2},  # Items 1 and 2 are already processed
        )

        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = MagicMock(spec=StateManager)
        mock_state_manager.get_batch_progress.return_value = existing_progress
        mock_state_manager.get_stale_unavailable_items.return_value = []

        # Create mock movies
        mock_movies = []
        for i in range(1, 4):
            m = MagicMock()
            m.id = i
            m.title = f"Movie {i}"
            mock_movies.append(m)

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli._fetch_movies_to_check") as mock_fetch,
            patch("filtarr.cli.get_checker") as mock_get_checker,
        ):
            mock_fetch.return_value = (mock_movies, set())
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = SearchResult(
                item_id=3, item_type="movie", has_match=True
            )
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                ["check", "batch", "--all-movies", "--format", "simple"],
            )

        # Should have skipped items 1 and 2, only processed item 3
        assert "Summary" in result.output


class TestBatchProgressClearing:
    """Tests for L1034 and L1042: Break from batch and clear progress on completion."""

    def test_batch_clears_progress_on_successful_completion(self) -> None:
        """Should clear batch progress when batch completes successfully."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = MagicMock(spec=StateManager)
        mock_state_manager.get_batch_progress.return_value = None
        mock_state_manager.get_stale_unavailable_items.return_value = []

        # Create a single mock movie
        mock_movie = MagicMock()
        mock_movie.id = 1
        mock_movie.title = "Test Movie"

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli._fetch_movies_to_check") as mock_fetch,
            patch("filtarr.cli.get_checker") as mock_get_checker,
        ):
            mock_fetch.return_value = ([mock_movie], set())
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = SearchResult(
                item_id=1, item_type="movie", has_match=True
            )
            mock_get_checker.return_value = mock_checker

            runner.invoke(
                app,
                ["check", "batch", "--all-movies", "--format", "simple"],
            )

        # Should have cleared batch progress on successful completion
        mock_state_manager.clear_batch_progress.assert_called_once()

    def test_batch_does_not_clear_progress_when_batch_limit_reached(self) -> None:
        """Should NOT clear batch progress when batch limit is reached."""
        mock_config = Config(radarr=RadarrConfig(url="http://localhost:7878", api_key="key"))
        mock_state_manager = MagicMock(spec=StateManager)
        mock_state_manager.get_batch_progress.return_value = None
        mock_state_manager.get_stale_unavailable_items.return_value = []

        # Create a new BatchProgress to be returned by start_batch
        new_progress = BatchProgress(batch_id="new-batch", item_type="movie", total_items=5)
        mock_state_manager.start_batch.return_value = new_progress

        # Create multiple mock movies
        mock_movies = []
        for i in range(1, 6):
            m = MagicMock()
            m.id = i
            m.title = f"Movie {i}"
            mock_movies.append(m)

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli._fetch_movies_to_check") as mock_fetch,
            patch("filtarr.cli.get_checker") as mock_get_checker,
        ):
            mock_fetch.return_value = (mock_movies, set())
            mock_checker = AsyncMock()
            # Return a different result for each movie ID
            mock_checker.check_movie.side_effect = lambda movie_id, **_: SearchResult(
                item_id=movie_id, item_type="movie", has_match=True
            )
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                [
                    "check",
                    "batch",
                    "--all-movies",
                    "--batch-size",
                    "2",  # Limit to 2 items
                    "--format",
                    "simple",
                ],
            )

        # Should NOT have cleared batch progress since batch limit was reached
        mock_state_manager.clear_batch_progress.assert_not_called()
        assert "batch limit" in result.output.lower()


class TestRunBatchChecksNewProgress:
    """Tests for L1004-1006: Creating new batch_progress."""

    @pytest.mark.asyncio
    async def test_run_batch_checks_creates_new_progress_when_none_exists(
        self,
        mock_config: Config,
        real_console: Console,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should create new batch progress when no existing progress."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=real_console,
            error_console=real_console,
        )

        # Create mock movies
        mock_movie = MagicMock()
        mock_movie.id = 1
        mock_movie.title = "Test Movie"

        new_progress = BatchProgress(batch_id="new-batch", item_type="movie", total_items=1)
        mock_state_manager.start_batch.return_value = new_progress

        with (
            patch("filtarr.cli._fetch_movies_to_check", return_value=([mock_movie], set())),
            patch("filtarr.cli._process_single_item", return_value=True),
        ):
            await _run_batch_checks(
                ctx,
                all_movies=True,
                all_series=False,
                skip_tagged=False,
                file_items=[],
                batch_type="movie",
                existing_progress=None,
            )

        # Should have started a new batch
        mock_state_manager.start_batch.assert_called_once()
        # Batch ID should be 8 characters (UUID[:8])
        call_args = mock_state_manager.start_batch.call_args
        assert len(call_args[0][0]) == 8  # batch_id
        assert call_args[0][1] == "movie"  # batch_type
        assert call_args[0][2] == 1  # total_items

    @pytest.mark.asyncio
    async def test_run_batch_checks_uses_existing_progress(
        self,
        mock_config: Config,
        real_console: Console,
        mock_state_manager: MagicMock,
    ) -> None:
        """Should use existing progress when provided."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=real_console,
            error_console=real_console,
        )

        mock_movie = MagicMock()
        mock_movie.id = 1
        mock_movie.title = "Test Movie"

        existing_progress = BatchProgress(
            batch_id="existing-batch",
            item_type="movie",
            total_items=5,
            processed_ids={1},
        )

        with (
            patch("filtarr.cli._fetch_movies_to_check", return_value=([mock_movie], set())),
            patch("filtarr.cli._process_single_item", return_value=True),
        ):
            await _run_batch_checks(
                ctx,
                all_movies=True,
                all_series=False,
                skip_tagged=False,
                file_items=[],
                batch_type="movie",
                existing_progress=existing_progress,
            )

        # Should NOT have started a new batch
        mock_state_manager.start_batch.assert_not_called()


class TestBatchProgressBarShowsBatchSize:
    """Tests for progress bar showing batch size instead of total items."""

    @pytest.mark.asyncio
    async def test_progress_bar_total_is_batch_size_when_set(
        self,
        mock_config: Config,
        real_console: Console,
        mock_state_manager: MagicMock,
    ) -> None:
        """When batch_size is set, progress bar total should be min(batch_size, total_items)."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=5,  # Batch size of 5
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=real_console,
            error_console=real_console,
        )

        # Create 100 mock movies (more than batch size)
        mock_movies = []
        for i in range(1, 101):
            m = MagicMock()
            m.id = i
            m.title = f"Movie {i}"
            mock_movies.append(m)

        new_progress = BatchProgress(batch_id="new-batch", item_type="movie", total_items=100)
        mock_state_manager.start_batch.return_value = new_progress

        # Track how many items are actually processed
        processed_count = 0

        async def mock_process_single(*_args: Any, **_kwargs: Any) -> bool:
            nonlocal processed_count
            processed_count += 1
            # Simulate successful processing
            ctx.processed_this_run += 1
            ctx.results.append(
                SearchResult(item_id=processed_count, item_type="movie", has_match=True)
            )
            # Return False when batch limit reached
            if ctx.batch_size > 0 and ctx.processed_this_run >= ctx.batch_size:
                ctx.batch_limit_reached = True
                return False
            return True

        with (
            patch("filtarr.cli._fetch_movies_to_check", return_value=(mock_movies, set())),
            patch("filtarr.cli._process_single_item", side_effect=mock_process_single),
        ):
            await _run_batch_checks(
                ctx,
                all_movies=True,
                all_series=False,
                skip_tagged=False,
                file_items=[],
                batch_type="movie",
                existing_progress=None,
            )

        # Should have only processed batch_size items (5), not all 100
        assert processed_count == 5
        assert ctx.batch_limit_reached is True
        assert len(ctx.results) == 5

    @pytest.mark.asyncio
    async def test_progress_bar_total_is_all_items_when_batch_size_zero(
        self,
        mock_config: Config,
        real_console: Console,
        mock_state_manager: MagicMock,
    ) -> None:
        """When batch_size is 0 (unlimited), progress bar total should be total items."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,  # Unlimited
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=real_console,
            error_console=real_console,
        )

        # Create 10 mock movies
        mock_movies = []
        for i in range(1, 11):
            m = MagicMock()
            m.id = i
            m.title = f"Movie {i}"
            mock_movies.append(m)

        new_progress = BatchProgress(batch_id="new-batch", item_type="movie", total_items=10)
        mock_state_manager.start_batch.return_value = new_progress

        processed_count = 0

        async def mock_process_single(*_args: Any, **_kwargs: Any) -> bool:
            nonlocal processed_count
            processed_count += 1
            ctx.results.append(
                SearchResult(item_id=processed_count, item_type="movie", has_match=True)
            )
            return True

        with (
            patch("filtarr.cli._fetch_movies_to_check", return_value=(mock_movies, set())),
            patch("filtarr.cli._process_single_item", side_effect=mock_process_single),
        ):
            await _run_batch_checks(
                ctx,
                all_movies=True,
                all_series=False,
                skip_tagged=False,
                file_items=[],
                batch_type="movie",
                existing_progress=None,
            )

        # Should have processed all 10 items
        assert processed_count == 10
        assert ctx.batch_limit_reached is False
        assert len(ctx.results) == 10

    @pytest.mark.asyncio
    async def test_progress_bar_total_uses_items_count_when_less_than_batch_size(
        self,
        mock_config: Config,
        real_console: Console,
        mock_state_manager: MagicMock,
    ) -> None:
        """When total items < batch_size, progress bar total should be total items."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=100,  # Batch size larger than items
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=real_console,
            error_console=real_console,
        )

        # Create only 3 mock movies (less than batch size of 100)
        mock_movies = []
        for i in range(1, 4):
            m = MagicMock()
            m.id = i
            m.title = f"Movie {i}"
            mock_movies.append(m)

        new_progress = BatchProgress(batch_id="new-batch", item_type="movie", total_items=3)
        mock_state_manager.start_batch.return_value = new_progress

        processed_count = 0

        async def mock_process_single(*_args: Any, **_kwargs: Any) -> bool:
            nonlocal processed_count
            processed_count += 1
            ctx.results.append(
                SearchResult(item_id=processed_count, item_type="movie", has_match=True)
            )
            return True

        with (
            patch("filtarr.cli._fetch_movies_to_check", return_value=(mock_movies, set())),
            patch("filtarr.cli._process_single_item", side_effect=mock_process_single),
        ):
            await _run_batch_checks(
                ctx,
                all_movies=True,
                all_series=False,
                skip_tagged=False,
                file_items=[],
                batch_type="movie",
                existing_progress=None,
            )

        # Should have processed all 3 items (less than batch_size of 100)
        assert processed_count == 3
        assert ctx.batch_limit_reached is False
        assert len(ctx.results) == 3


# =============================================================================
# TESTS FOR ERROR COLLECTION IN BATCH SUMMARY (Task 7)
# =============================================================================


class TestFormatErrorMessage:
    """Tests for _format_error_message helper function."""

    def test_format_http_status_error(self) -> None:
        """Should format HTTP status errors as 'HTTP XXX'."""
        from filtarr.cli import _format_error_message

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_request = MagicMock()

        error = httpx.HTTPStatusError("Not Found", request=mock_request, response=mock_response)

        result = _format_error_message(error)
        assert result == "HTTP 404"

    def test_format_connect_error(self) -> None:
        """Should format connection errors as 'Connection failed'."""
        from filtarr.cli import _format_error_message

        error = httpx.ConnectError("Connection refused")

        result = _format_error_message(error)
        assert result == "Connection failed"

    def test_format_timeout_error(self) -> None:
        """Should format timeout errors as 'Request timed out'."""
        from filtarr.cli import _format_error_message

        error = httpx.TimeoutException("Timeout")

        result = _format_error_message(error)
        assert result == "Request timed out"

    def test_format_configuration_error(self) -> None:
        """Should format configuration errors with their message."""
        from filtarr.cli import _format_error_message

        error = ConfigurationError("Radarr not configured")

        result = _format_error_message(error)
        assert result == "Radarr not configured"

    def test_format_generic_error(self) -> None:
        """Should format generic errors with str()."""
        from filtarr.cli import _format_error_message

        error = RuntimeError("Something went wrong")

        result = _format_error_message(error)
        assert result == "Something went wrong"


class TestBatchErrorCollectionInSummary:
    """Tests for error collection and display in batch summary."""

    @pytest.mark.asyncio
    async def test_errors_collected_during_processing(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Errors should be collected in the formatter during batch processing."""

        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_request = MagicMock()

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=httpx.HTTPStatusError(
                "Internal Server Error", request=mock_request, response=mock_response
            ),
        ):
            await _process_single_item(ctx, "movie", 123, "Test Movie", batch_progress=None)

        # Error should be collected in formatter
        assert len(ctx.formatter.errors) == 1
        assert ctx.formatter.errors[0] == ("Test Movie", "HTTP 500")

    @pytest.mark.asyncio
    async def test_multiple_errors_collected(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Multiple errors should be collected in the formatter."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # Simulate different types of errors
        errors = [
            httpx.ConnectError("Connection refused"),
            httpx.TimeoutException("Timeout"),
            ConfigurationError("API key missing"),
        ]

        for i, error in enumerate(errors):
            with patch("filtarr.cli._process_batch_item", side_effect=error):
                await _process_single_item(
                    ctx, "movie", i + 1, f"Movie {i + 1}", batch_progress=None
                )

        # All errors should be collected
        assert len(ctx.formatter.errors) == 3
        assert ctx.formatter.errors[0] == ("Movie 1", "Connection failed")
        assert ctx.formatter.errors[1] == ("Movie 2", "Request timed out")
        assert ctx.formatter.errors[2] == ("Movie 3", "API key missing")

    def test_batch_summary_with_no_errors(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Batch summary should not show error section if no errors."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # No errors added

        # Get format_summary output
        summary_lines = ctx.formatter.format_summary()

        # Should be empty if no errors
        assert len(summary_lines) == 0

    @pytest.mark.asyncio
    async def test_error_uses_display_name_for_named_items(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Error collection should use the item name for named items."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            await _process_single_item(ctx, "movie", 123, "The Matrix", batch_progress=None)

        # Should use the item name, not "movie:123"
        assert len(ctx.formatter.errors) == 1
        assert ctx.formatter.errors[0][0] == "The Matrix"

    @pytest.mark.asyncio
    async def test_error_uses_type_and_id_for_id_prefix_items(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """Error collection should use type:id for items with ID: prefix."""
        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        with patch(
            "filtarr.cli._process_batch_item",
            side_effect=httpx.TimeoutException("Timeout"),
        ):
            await _process_single_item(ctx, "movie", 456, "ID:456", batch_progress=None)

        # Should use "movie:456" since item_name starts with "ID:"
        assert len(ctx.formatter.errors) == 1
        assert ctx.formatter.errors[0][0] == "movie:456"


class TestBatchContextFormatterInitialization:
    """Tests for BatchContext formatter initialization."""

    def test_batch_context_has_formatter_by_default(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """BatchContext should have an OutputFormatter by default."""
        from filtarr.output import OutputFormatter

        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # Should have a formatter
        assert ctx.formatter is not None
        assert isinstance(ctx.formatter, OutputFormatter)
        assert ctx.formatter.errors == []
        assert ctx.formatter.warnings == []


class TestPrintBatchSummary:
    """Tests for _print_batch_summary output formatting."""

    def test_print_batch_summary_with_warnings(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """_print_batch_summary should print warnings in yellow."""
        from filtarr.cli import _print_batch_summary

        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # Add a warning to the formatter
        ctx.formatter.add_warning("Slow request (15s)")

        # Call _print_batch_summary
        with patch("filtarr.cli.console") as patched_console:
            _print_batch_summary(ctx)

            # Check that warnings are printed with yellow formatting
            calls = [str(c) for c in patched_console.print.call_args_list]
            # Should contain a call with yellow and "Warnings"
            assert any("[yellow]" in c and "Warnings" in c for c in calls)

    def test_print_batch_summary_with_errors(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """_print_batch_summary should print errors in red."""
        from filtarr.cli import _print_batch_summary

        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # Add an error to the formatter
        ctx.formatter.add_error("The Matrix", "HTTP 404")

        # Call _print_batch_summary
        with patch("filtarr.cli.console") as patched_console:
            _print_batch_summary(ctx)

            # Check that errors are printed with red formatting
            calls = [str(c) for c in patched_console.print.call_args_list]
            # Should contain a call with red and "Errors"
            assert any("[red]" in c and "Errors" in c for c in calls)
            # Should contain detail lines with dim formatting
            assert any("[dim]" in c and "The Matrix" in c for c in calls)

    def test_print_batch_summary_with_warnings_and_errors(
        self,
        mock_config: Config,
        mock_console: Any,
        mock_error_console: Any,
        mock_state_manager: MagicMock,
    ) -> None:
        """_print_batch_summary should print both warnings and errors."""
        from filtarr.cli import _print_batch_summary

        ctx = BatchContext(
            config=mock_config,
            state_manager=mock_state_manager,
            search_criteria=SearchCriteria.FOUR_K,
            criteria_str="4k",
            sampling_strategy=SamplingStrategy.RECENT,
            seasons=3,
            apply_tags=False,
            dry_run=False,
            batch_size=0,
            delay=0,
            output_format=OutputFormat.SIMPLE,
            console=mock_console,
            error_console=mock_error_console,
        )

        # Add warnings and errors
        ctx.formatter.add_warning("Slow request")
        ctx.formatter.add_error("Movie 1", "Connection failed")

        # Call _print_batch_summary
        with patch("filtarr.cli.console") as patched_console:
            _print_batch_summary(ctx)

            calls = [str(c) for c in patched_console.print.call_args_list]
            # Both warnings and errors should be printed
            assert any("[yellow]" in c and "Warnings" in c for c in calls)
            assert any("[red]" in c and "Errors" in c for c in calls)
