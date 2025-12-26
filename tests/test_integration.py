"""Integration tests for filtarr.

These tests verify the full flow from high-level API through to mocked HTTP responses.
They are marked with @pytest.mark.integration for selective running.
"""

from datetime import date, timedelta

import pytest
import respx
from httpx import Response

from filtarr import ReleaseChecker, SamplingStrategy, SearchResult


@pytest.mark.integration
class TestMovieCheckIntegration:
    """End-to-end tests for movie 4K checking."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_with_4k_available(self) -> None:
        """Full flow: check movie by ID, find 4K releases."""
        # Mock the movie info endpoint
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(200, json={"id": 123, "title": "Test Movie", "year": 2024})
        )

        # Mock the release search endpoint
        respx.get(
            "http://localhost:7878/api/v3/release",
            params={"movieId": "123"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "release-4k-1",
                        "title": "Movie.2024.2160p.UHD.BluRay.x265-GROUP",
                        "indexer": "Indexer1",
                        "size": 50_000_000_000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    },
                    {
                        "guid": "release-1080p-1",
                        "title": "Movie.2024.1080p.BluRay.x264-GROUP",
                        "indexer": "Indexer1",
                        "size": 15_000_000_000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    },
                ],
            )
        )

        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        result = await checker.check_movie(123, apply_tags=False)

        assert isinstance(result, SearchResult)
        assert result.has_match is True
        assert result.item_id == 123
        assert result.item_type == "movie"
        assert len(result.releases) == 2
        assert len(result.matched_releases) == 1
        assert result.matched_releases[0].title == "Movie.2024.2160p.UHD.BluRay.x265-GROUP"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name_flow(self) -> None:
        """Full flow: search movie by name, then check for 4K."""
        # Mock get all movies
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 100, "title": "The Matrix", "year": 1999},
                    {"id": 101, "title": "The Matrix Reloaded", "year": 2003},
                    {"id": 102, "title": "Inception", "year": 2010},
                ],
            )
        )

        # Mock movie info for found movie
        respx.get("http://localhost:7878/api/v3/movie/100").mock(
            return_value=Response(200, json={"id": 100, "title": "The Matrix", "year": 1999})
        )

        # Mock release search for found movie
        respx.get(
            "http://localhost:7878/api/v3/release",
            params={"movieId": "100"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "matrix-4k",
                        "title": "The.Matrix.1999.2160p.UHD",
                        "indexer": "Test",
                        "size": 60_000_000_000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    },
                ],
            )
        )

        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        # Search for movie
        matches = await checker.search_movies("Matrix")
        assert len(matches) == 2
        assert matches[0] == (100, "The Matrix", 1999)

        # Check the first match
        result = await checker.check_movie(matches[0][0], apply_tags=False)
        assert result.has_match is True
        assert result.item_id == 100


@pytest.mark.integration
class TestSeriesCheckIntegration:
    """End-to-end tests for series 4K checking with sampling."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_recent_strategy(self) -> None:
        """Full flow: check series with RECENT strategy, sampling last 2 seasons."""
        today = date.today()
        last_week = today - timedelta(days=7)

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200, json={"id": 456, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        # Mock episodes endpoint
        respx.get(
            "http://127.0.0.1:8989/api/v3/episode",
            params={"seriesId": "456"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    # Season 1
                    {
                        "id": 1001,
                        "seriesId": 456,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-15",
                        "monitored": True,
                    },
                    {
                        "id": 1002,
                        "seriesId": 456,
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "airDate": "2020-01-22",
                        "monitored": True,
                    },
                    # Season 2
                    {
                        "id": 2001,
                        "seriesId": 456,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-15",
                        "monitored": True,
                    },
                    {
                        "id": 2002,
                        "seriesId": 456,
                        "seasonNumber": 2,
                        "episodeNumber": 2,
                        "airDate": "2021-01-22",
                        "monitored": True,
                    },
                    # Season 3 (most recent)
                    {
                        "id": 3001,
                        "seriesId": 456,
                        "seasonNumber": 3,
                        "episodeNumber": 1,
                        "airDate": last_week.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        # Mock releases for season 2 latest episode (no 4K)
        respx.get(
            "http://127.0.0.1:8989/api/v3/release",
            params={"episodeId": "2002"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "s02e02-1080p",
                        "title": "Show.S02E02.1080p",
                        "indexer": "Test",
                        "size": 2_000_000_000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    },
                ],
            )
        )

        # Mock releases for season 3 latest episode (has 4K!)
        respx.get(
            "http://127.0.0.1:8989/api/v3/release",
            params={"episodeId": "3001"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "s03e01-4k",
                        "title": "Show.S03E01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5_000_000_000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    },
                ],
            )
        )

        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test-key",
        )

        result = await checker.check_series(
            456,
            strategy=SamplingStrategy.RECENT,
            seasons_to_check=2,
            apply_tags=False,
        )

        assert result.has_match is True
        assert result.item_type == "series"
        assert result.strategy_used == SamplingStrategy.RECENT
        # Should have checked seasons 2 and 3 (most recent 2)
        assert set(result.seasons_checked) == {2, 3}

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_distributed_strategy(self) -> None:
        """Full flow: check series with DISTRIBUTED strategy (first, middle, last)."""
        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/789").mock(
            return_value=Response(
                200, json={"id": 789, "title": "Long Series", "year": 2019, "seasons": []}
            )
        )

        # Mock episodes for 5 seasons
        respx.get(
            "http://127.0.0.1:8989/api/v3/episode",
            params={"seriesId": "789"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 789,
                        "seasonNumber": 1,
                        "episodeNumber": 10,
                        "airDate": "2019-03-15",
                        "monitored": True,
                    },
                    {
                        "id": 2001,
                        "seriesId": 789,
                        "seasonNumber": 2,
                        "episodeNumber": 10,
                        "airDate": "2020-03-15",
                        "monitored": True,
                    },
                    {
                        "id": 3001,
                        "seriesId": 789,
                        "seasonNumber": 3,
                        "episodeNumber": 10,
                        "airDate": "2021-03-15",
                        "monitored": True,
                    },
                    {
                        "id": 4001,
                        "seriesId": 789,
                        "seasonNumber": 4,
                        "episodeNumber": 10,
                        "airDate": "2022-03-15",
                        "monitored": True,
                    },
                    {
                        "id": 5001,
                        "seriesId": 789,
                        "seasonNumber": 5,
                        "episodeNumber": 10,
                        "airDate": "2023-03-15",
                        "monitored": True,
                    },
                ],
            )
        )

        # Mock releases for seasons 1, 3, 5 (first, middle, last) - all no 4K
        for ep_id in [1001, 3001, 5001]:
            respx.get(
                "http://127.0.0.1:8989/api/v3/release",
                params={"episodeId": str(ep_id)},
            ).mock(
                return_value=Response(
                    200,
                    json=[
                        {
                            "guid": f"ep-{ep_id}-1080p",
                            "title": "Show.S0X.E10.1080p",
                            "indexer": "Test",
                            "size": 2_000_000_000,
                            "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                        },
                    ],
                )
            )

        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test-key",
        )

        result = await checker.check_series(
            789, strategy=SamplingStrategy.DISTRIBUTED, apply_tags=False
        )

        assert result.has_match is False
        assert result.strategy_used == SamplingStrategy.DISTRIBUTED
        # Should have checked first (1), middle (3), and last (5) seasons
        assert sorted(result.seasons_checked) == [1, 3, 5]

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_by_name_flow(self) -> None:
        """Full flow: search series by name, then check for 4K."""
        # Mock get all series
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 500, "title": "Breaking Bad", "year": 2008, "seasons": []},
                    {"id": 501, "title": "Better Call Saul", "year": 2015, "seasons": []},
                ],
            )
        )

        # Mock series info for Breaking Bad
        respx.get("http://127.0.0.1:8989/api/v3/series/500").mock(
            return_value=Response(
                200, json={"id": 500, "title": "Breaking Bad", "year": 2008, "seasons": []}
            )
        )

        # Mock episodes for Breaking Bad
        respx.get(
            "http://127.0.0.1:8989/api/v3/episode",
            params={"seriesId": "500"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 5001,
                        "seriesId": 500,
                        "seasonNumber": 5,
                        "episodeNumber": 16,
                        "airDate": "2013-09-29",
                        "monitored": True,
                    },
                ],
            )
        )

        # Mock releases
        respx.get(
            "http://127.0.0.1:8989/api/v3/release",
            params={"episodeId": "5001"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "bb-4k",
                        "title": "Breaking.Bad.S05E16.2160p.UHD",
                        "indexer": "Test",
                        "size": 8_000_000_000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    },
                ],
            )
        )

        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test-key",
        )

        # Search for series
        matches = await checker.search_series("Breaking")
        assert len(matches) == 1
        assert matches[0] == (500, "Breaking Bad", 2008)

        # Check the match
        result = await checker.check_series(matches[0][0], apply_tags=False)
        assert result.has_match is True


@pytest.mark.integration
class TestCombinedCheckerIntegration:
    """Tests for ReleaseChecker with both Radarr and Sonarr configured."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_checker_with_both_services(self) -> None:
        """Should be able to check both movies and series with same checker."""
        # Mock movie info
        respx.get("http://localhost:7878/api/v3/movie/10").mock(
            return_value=Response(200, json={"id": 10, "title": "Some Movie", "year": 2023})
        )

        # Mock movie releases
        respx.get(
            "http://localhost:7878/api/v3/release",
            params={"movieId": "10"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "movie-4k",
                        "title": "Movie.2160p",
                        "indexer": "Test",
                        "size": 50_000_000_000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    },
                ],
            )
        )

        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/20").mock(
            return_value=Response(
                200, json={"id": 20, "title": "Some Series", "year": 2023, "seasons": []}
            )
        )

        # Mock series episodes
        respx.get(
            "http://127.0.0.1:8989/api/v3/episode",
            params={"seriesId": "20"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 2001,
                        "seriesId": 20,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2023-01-01",
                        "monitored": True,
                    },
                ],
            )
        )

        # Mock series releases
        respx.get(
            "http://127.0.0.1:8989/api/v3/release",
            params={"episodeId": "2001"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "series-1080p",
                        "title": "Series.S01E01.1080p",
                        "indexer": "Test",
                        "size": 2_000_000_000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    },
                ],
            )
        )

        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="radarr-key",
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="sonarr-key",
        )

        movie_result = await checker.check_movie(10, apply_tags=False)
        series_result = await checker.check_series(20, apply_tags=False)

        assert movie_result.has_match is True
        assert movie_result.item_type == "movie"
        assert series_result.has_match is False
        assert series_result.item_type == "series"


@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Tests for error handling in integration scenarios."""

    @pytest.mark.asyncio
    async def test_check_movie_without_radarr_config(self) -> None:
        """Should raise ValueError when checking movie without Radarr configured."""
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="key",
        )

        with pytest.raises(ValueError, match="Radarr is not configured"):
            await checker.check_movie(123)

    @pytest.mark.asyncio
    async def test_check_series_without_sonarr_config(self) -> None:
        """Should raise ValueError when checking series without Sonarr configured."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="key",
        )

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            await checker.check_series(456)

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_empty_release_response(self) -> None:
        """Should handle case where no releases are found."""
        # Mock movie info
        respx.get("http://localhost:7878/api/v3/movie/999").mock(
            return_value=Response(200, json={"id": 999, "title": "Empty Movie", "year": 2024})
        )

        respx.get(
            "http://localhost:7878/api/v3/release",
            params={"movieId": "999"},
        ).mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="key",
        )

        result = await checker.check_movie(999, apply_tags=False)

        assert result.has_match is False
        assert result.releases == []
