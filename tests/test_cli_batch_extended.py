"""Extended tests for CLI batch processing edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response
from rich.console import Console

from filtarr.checker import ReleaseChecker, SamplingStrategy
from filtarr.cli import (
    _fetch_movies_to_check,
    _fetch_series_to_check,
    _process_movie_item,
    _process_series_item,
)
from filtarr.config import Config, RadarrConfig, SonarrConfig, TagConfig
from filtarr.criteria import SearchCriteria


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
def mock_console() -> Console:
    """Create a mock console for testing."""
    console = MagicMock(spec=Console)
    console.print = MagicMock()
    return console


@pytest.fixture
def mock_error_console() -> Console:
    """Create a mock error console for testing."""
    console = MagicMock(spec=Console)
    console.print = MagicMock()
    return console


class TestFetchMoviesToCheck:
    """Tests for _fetch_movies_to_check function."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_movies_skip_tagged_true_filters_movies(
        self, mock_config: Config, mock_console: Console
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
        self, mock_config: Config, mock_console: Console
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
        self, mock_config: Config, mock_console: Console
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
        self, mock_config: Config, mock_console: Console
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
        self, mock_config: Config, mock_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
        self, mock_console: Console, mock_error_console: Console
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
