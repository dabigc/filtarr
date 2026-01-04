"""Tests for ReleaseChecker and sampling strategies."""

from datetime import date, timedelta

import httpx
import pytest
import respx
from httpx import Response

from filtarr.checker import (
    ReleaseChecker,
    SamplingStrategy,
    SearchResult,
    select_seasons_to_check,
)


class TestSelectSeasonsToCheck:
    """Unit tests for the select_seasons_to_check function."""

    def test_recent_strategy_returns_last_n_seasons(self) -> None:
        """RECENT strategy should return the most recent N seasons."""
        available = [1, 2, 3, 4, 5]
        result = select_seasons_to_check(available, SamplingStrategy.RECENT, max_seasons=3)
        assert result == [3, 4, 5]

    def test_recent_strategy_with_fewer_seasons_than_requested(self) -> None:
        """RECENT with 2 seasons should return all when asking for 3."""
        available = [1, 2]
        result = select_seasons_to_check(available, SamplingStrategy.RECENT, max_seasons=3)
        assert result == [1, 2]

    def test_distributed_strategy_selects_first_middle_last(self) -> None:
        """DISTRIBUTED should select first, middle, and last seasons."""
        available = [1, 2, 3, 4, 5]
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)
        assert result == [1, 3, 5]  # first, middle, last

    def test_distributed_strategy_with_two_seasons(self) -> None:
        """DISTRIBUTED with 2 seasons should return both."""
        available = [1, 2]
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)
        assert result == [1, 2]

    def test_distributed_strategy_with_one_season(self) -> None:
        """DISTRIBUTED with 1 season should return just that season."""
        available = [3]
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)
        assert result == [3]

    def test_all_strategy_returns_all_seasons(self) -> None:
        """ALL strategy should return all seasons."""
        available = [1, 2, 3, 4, 5]
        result = select_seasons_to_check(available, SamplingStrategy.ALL)
        assert result == [1, 2, 3, 4, 5]

    def test_empty_seasons_returns_empty(self) -> None:
        """Empty input should return empty list."""
        result = select_seasons_to_check([], SamplingStrategy.RECENT)
        assert result == []

    def test_unsorted_input_is_handled(self) -> None:
        """Should handle unsorted season numbers."""
        available = [5, 1, 3, 2, 4]
        result = select_seasons_to_check(available, SamplingStrategy.RECENT, max_seasons=2)
        assert result == [4, 5]


class TestMediaTypeEnum:
    """Tests for MediaType enum."""

    def test_media_type_movie_value_is_string_movie(self) -> None:
        """MediaType.MOVIE.value should be 'movie'."""
        from filtarr.checker import MediaType

        assert MediaType.MOVIE.value == "movie"

    def test_media_type_series_value_is_string_series(self) -> None:
        """MediaType.SERIES.value should be 'series'."""
        from filtarr.checker import MediaType

        assert MediaType.SERIES.value == "series"

    def test_media_type_is_str_subclass(self) -> None:
        """MediaType should be a StrEnum (subclass of str) for JSON serialization."""
        from filtarr.checker import MediaType

        # StrEnum instances should be str instances
        assert isinstance(MediaType.MOVIE, str)
        assert isinstance(MediaType.SERIES, str)

    def test_media_type_string_comparison(self) -> None:
        """MediaType values should compare equal to their string equivalents."""
        from filtarr.checker import MediaType

        assert MediaType.MOVIE == "movie"
        assert MediaType.SERIES == "series"

    def test_media_type_in_dict_key(self) -> None:
        """MediaType should work as dictionary key and serialize to string."""
        from filtarr.checker import MediaType

        data = {MediaType.MOVIE: "movie_value", MediaType.SERIES: "series_value"}
        # String keys should work to access the same values due to StrEnum
        assert data["movie"] == "movie_value"
        assert data["series"] == "series_value"


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_item_type_is_media_type_enum(self) -> None:
        """SearchResult.item_type should accept MediaType enum."""
        from filtarr.checker import MediaType

        result = SearchResult(
            item_id=123,
            item_type=MediaType.MOVIE,
            has_match=True,
        )
        assert result.item_type == MediaType.MOVIE
        assert result.item_type == "movie"  # StrEnum comparison

    def test_search_result_item_type_serializes_to_string(self) -> None:
        """SearchResult with MediaType should serialize to string for JSON output."""
        import json

        from filtarr.checker import MediaType

        result = SearchResult(
            item_id=123,
            item_type=MediaType.SERIES,
            has_match=False,
        )
        # When using StrEnum, str() should return the string value
        assert str(result.item_type) == "series"
        # JSON serialization should work (StrEnum is str subclass)
        data = {"item_type": result.item_type}
        json_str = json.dumps(data)
        assert '"series"' in json_str

    def test_matched_releases_property(self) -> None:
        """Should filter to only 4K releases."""
        from filtarr.checker import MediaType
        from filtarr.models.common import Quality, Release

        releases = [
            Release(
                guid="1",
                title="Movie.2160p",
                indexer="Test",
                size=1000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
            Release(
                guid="2",
                title="Movie.1080p",
                indexer="Test",
                size=500,
                quality=Quality(id=7, name="Bluray-1080p"),
            ),
            Release(
                guid="3",
                title="Movie.4K.HDR",
                indexer="Test",
                size=1500,
                quality=Quality(id=31, name="Bluray-2160p"),
            ),
        ]

        result = SearchResult(
            item_id=123,
            item_type=MediaType.MOVIE,
            has_match=True,
            releases=releases,
        )

        matched = result.matched_releases
        assert len(matched) == 2
        assert all(r.is_4k() for r in matched)


class TestCheckSeriesWithSampling:
    """Integration tests for check_series with sampling strategies."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_recent_strategy(self) -> None:
        """Should check latest episodes from recent seasons."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        # Mock episodes endpoint
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    # Season 1 episodes
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 102,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "airDate": "2020-01-08",
                        "monitored": True,
                    },
                    # Season 2 episodes
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                    # Season 3 episodes
                    {
                        "id": 301,
                        "seriesId": 123,
                        "seasonNumber": 3,
                        "episodeNumber": 1,
                        "airDate": "2022-01-01",
                        "monitored": True,
                    },
                    # Season 4 episodes
                    {
                        "id": 401,
                        "seriesId": 123,
                        "seasonNumber": 4,
                        "episodeNumber": 1,
                        "airDate": "2023-01-01",
                        "monitored": True,
                    },
                    # Season 5 episodes (most recent)
                    {
                        "id": 501,
                        "seriesId": 123,
                        "seasonNumber": 5,
                        "episodeNumber": 1,
                        "airDate": yesterday.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        # Mock release endpoints - no 4K releases
        for ep_id in [301, 401, 501]:  # Latest 3 seasons
            respx.get(
                "http://127.0.0.1:8989/api/v3/release", params={"episodeId": str(ep_id)}
            ).mock(
                return_value=Response(
                    200,
                    json=[
                        {
                            "guid": f"rel-{ep_id}",
                            "title": "Show.S0X.1080p",
                            "indexer": "Test",
                            "size": 1000,
                            "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                        }
                    ],
                )
            )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(
            123, strategy=SamplingStrategy.RECENT, seasons_to_check=3, apply_tags=False
        )

        assert result.has_match is False
        assert result.strategy_used == SamplingStrategy.RECENT
        assert sorted(result.seasons_checked) == [3, 4, 5]
        assert len(result.episodes_checked) == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_short_circuits_on_4k(self) -> None:
        """Should stop checking after finding 4K."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
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
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 301,
                        "seriesId": 123,
                        "seasonNumber": 3,
                        "episodeNumber": 1,
                        "airDate": yesterday.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        # First season checked (season 1) - no 4K
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        # Second season (season 2) - has 4K!
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "201"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-201-4k",
                        "title": "Show.S02.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        # Season 3 should NOT be called due to short-circuit
        # (we don't mock it - if called, test would fail)

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, strategy=SamplingStrategy.ALL, apply_tags=False)

        assert result.has_match is True
        # Should have stopped after finding 4K in season 2
        assert result.seasons_checked == [1, 2]
        assert len(result.episodes_checked) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_no_aired_episodes(self) -> None:
        """Should return empty result when no episodes have aired."""
        tomorrow = date.today() + timedelta(days=1)

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
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
                        "airDate": tomorrow.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, apply_tags=False)

        assert result.has_match is False
        assert result.episodes_checked == []
        assert result.seasons_checked == []
        assert result.strategy_used == SamplingStrategy.RECENT

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_distributed_strategy(self) -> None:
        """Should check first, middle, and last seasons with DISTRIBUTED."""
        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
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
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 301,
                        "seriesId": 123,
                        "seasonNumber": 3,
                        "episodeNumber": 1,
                        "airDate": "2022-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 401,
                        "seriesId": 123,
                        "seasonNumber": 4,
                        "episodeNumber": 1,
                        "airDate": "2023-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 501,
                        "seriesId": 123,
                        "seasonNumber": 5,
                        "episodeNumber": 1,
                        "airDate": "2024-01-01",
                        "monitored": True,
                    },
                ],
            )
        )

        # Mock releases for seasons 1, 3, 5 (first, middle, last)
        for ep_id in [101, 301, 501]:
            respx.get(
                "http://127.0.0.1:8989/api/v3/release", params={"episodeId": str(ep_id)}
            ).mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(
            123, strategy=SamplingStrategy.DISTRIBUTED, apply_tags=False
        )

        assert result.has_match is False
        assert result.strategy_used == SamplingStrategy.DISTRIBUTED
        assert sorted(result.seasons_checked) == [1, 3, 5]

    @pytest.mark.asyncio
    async def test_check_series_raises_when_not_configured(self) -> None:
        """Should raise ValueError when Sonarr not configured."""
        checker = ReleaseChecker()  # No Sonarr config

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            await checker.check_series(123)

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_still_works(self) -> None:
        """Verify check_movie still functions correctly."""
        # Mock movie info endpoint
        respx.get("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(200, json={"id": 456, "title": "Test Movie", "year": 2024})
        )

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "movie-rel",
                        "title": "Movie.2024.2160p.UHD",
                        "indexer": "Test",
                        "size": 15000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie(456, apply_tags=False)

        assert result.has_match is True
        assert result.item_type == "movie"
        assert result.item_id == 456

    @pytest.mark.asyncio
    async def test_check_movie_raises_when_not_configured(self) -> None:
        """Should raise ValueError when Radarr not configured."""
        checker = ReleaseChecker()  # No Radarr config

        with pytest.raises(ValueError, match="Radarr is not configured"):
            await checker.check_movie(456)


class TestNameBasedLookup:
    """Tests for name-based lookup functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_movies_returns_tuples(self) -> None:
        """Should return list of (id, title, year) tuples."""
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003},
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        results = await checker.search_movies("Matrix")

        assert len(results) == 2
        assert results[0] == (1, "The Matrix", 1999)
        assert results[1] == (2, "The Matrix Reloaded", 2003)

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_series_returns_tuples(self) -> None:
        """Should return list of (id, title, year) tuples."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []},
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        results = await checker.search_series("Breaking")

        assert len(results) == 1
        assert results[0] == (1, "Breaking Bad", 2008)

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name(self) -> None:
        """Should check movie by name."""
        # Mock search
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 123, "title": "The Matrix", "year": 1999}],
            )
        )
        # Mock releases
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-1",
                        "title": "The.Matrix.2160p.UHD",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie_by_name("The Matrix", apply_tags=False)

        assert result.has_match is True
        assert result.item_id == 123
        assert result.item_type == "movie"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name_not_found(self) -> None:
        """Should raise ValueError when movie not found."""
        respx.get("http://localhost:7878/api/v3/movie").mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        with pytest.raises(ValueError, match="Movie not found"):
            await checker.check_movie_by_name("Nonexistent Movie")

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name_with_tags(self) -> None:
        """Should check movie by name and apply tags."""
        # Mock search
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 123, "title": "The Matrix", "year": 1999, "tags": []}],
            )
        )
        # Mock movie by id (needed for tagging)
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "The Matrix", "year": 1999, "tags": []},
            )
        )
        # Mock releases - has 4K
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-1",
                        "title": "The.Matrix.2160p.UHD",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )
        # Mock tags endpoint
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(200, json=[{"id": 1, "label": "4k-available"}])
        )
        # Mock movie update
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "The Matrix", "year": 1999, "tags": [1]},
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie_by_name("The Matrix", apply_tags=True)

        assert result.has_match is True
        assert result.item_id == 123
        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-available"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_by_name(self) -> None:
        """Should check series by name."""
        # Mock search
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 456, "title": "Breaking Bad", "year": 2008, "seasons": []}],
            )
        )
        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200, json={"id": 456, "title": "Breaking Bad", "year": 2008, "seasons": []}
            )
        )
        # Mock episodes
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 456,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2008-01-20",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock releases
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "1001"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-1",
                        "title": "Breaking.Bad.S01E01.2160p",
                        "indexer": "Test",
                        "size": 3000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series_by_name("Breaking Bad", apply_tags=False)

        assert result.has_match is True
        assert result.item_id == 456
        assert result.item_type == "series"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_by_name_not_found(self) -> None:
        """Should raise ValueError when series not found."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        with pytest.raises(ValueError, match="Series not found"):
            await checker.check_series_by_name("Nonexistent Series")

    @pytest.mark.asyncio
    async def test_search_movies_raises_when_not_configured(self) -> None:
        """Should raise ValueError when Radarr not configured."""
        checker = ReleaseChecker()

        with pytest.raises(ValueError, match="Radarr is not configured"):
            await checker.search_movies("Test")

    @pytest.mark.asyncio
    async def test_search_series_raises_when_not_configured(self) -> None:
        """Should raise ValueError when Sonarr not configured."""
        checker = ReleaseChecker()

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            await checker.search_series("Test")


class TestTagApplication:
    """Tests for tag application logic in ReleaseChecker."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_creates_and_applies_tag(self) -> None:
        """Should create tag if not exists and apply to movie via check_movie."""
        from filtarr.config import TagConfig

        # Mock get_movie for name lookup
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        # Mock releases
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
        # Mock get_tags (empty - no existing tags)
        respx.get("http://localhost:7878/api/v3/tag").mock(return_value=Response(200, json=[]))
        # Mock create_tag
        respx.post("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-available"})
        )
        # Mock update_movie
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-available"
        assert result.tag_result.tag_created is True
        assert result.tag_result.tag_error is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_uses_existing_tag(self) -> None:
        """Should use existing tag without creating new one."""
        from filtarr.config import TagConfig

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
        # Mock get_tags (tag already exists)
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )
        # Mock update_movie
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-available"
        assert result.tag_result.tag_created is False
        assert result.tag_result.tag_error is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_removes_opposite_tag(self) -> None:
        """Should remove opposite tag when applying new one."""
        from filtarr.config import TagConfig

        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [2]},
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
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-available"
        assert result.tag_result.tag_removed == "4k-unavailable"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_dry_run_no_api_calls(self) -> None:
        """Should not make tag API calls in dry run mode."""
        from filtarr.config import TagConfig

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
        # No tag mocks needed - dry run shouldn't call them

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=True)

        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-available"
        assert result.tag_result.tag_removed == "4k-unavailable"
        assert result.tag_result.dry_run is True
        assert result.tag_result.tag_created is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_unavailable_applies_unavailable_tag(self) -> None:
        """Should apply unavailable tag when has_match is False."""
        from filtarr.config import TagConfig

        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        # No 4K releases
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie.1080p.BluRay",
                        "indexer": "Test",
                        "size": 2000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
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
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [2]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.has_match is False
        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-unavailable"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_no_tags_when_disabled(self) -> None:
        """Should not apply tags when apply_tags is False."""
        from filtarr.config import TagConfig

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
        # No tag mocks needed - tagging is disabled

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=False)

        assert result.has_match is True
        assert result.tag_result is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_tag_error_handling(self) -> None:
        """Should catch tag errors and return them in result."""
        from filtarr.config import TagConfig

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
        # Mock get_tags to fail
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(500, json={"error": "Server error"})
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        # Should still return result even if tagging failed
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_case_insensitive_tag_matching(self) -> None:
        """Should find tags case-insensitively."""
        from filtarr.config import TagConfig

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
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "label": "4K-Available"}],  # Different case
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        assert result.tag_result is not None
        assert result.tag_result.tag_applied == "4k-available"
        assert result.tag_result.tag_created is False  # Used existing tag


class TestMovieOnlyCriteriaEnforcement:
    """Tests for movie-only criteria enforcement in check_series."""

    @pytest.mark.asyncio
    async def test_check_series_rejects_directors_cut(self) -> None:
        """check_series should raise ValueError for DIRECTORS_CUT criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="DIRECTORS_CUT criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.DIRECTORS_CUT)

    @pytest.mark.asyncio
    async def test_check_series_rejects_extended(self) -> None:
        """check_series should raise ValueError for EXTENDED criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="EXTENDED criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.EXTENDED)

    @pytest.mark.asyncio
    async def test_check_series_rejects_remaster(self) -> None:
        """check_series should raise ValueError for REMASTER criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="REMASTER criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.REMASTER)

    @pytest.mark.asyncio
    async def test_check_series_rejects_imax(self) -> None:
        """check_series should raise ValueError for IMAX criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="IMAX criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.IMAX)

    @pytest.mark.asyncio
    async def test_check_series_rejects_special_edition(self) -> None:
        """check_series should raise ValueError for SPECIAL_EDITION criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        with pytest.raises(
            ValueError, match="SPECIAL_EDITION criteria is only applicable to movies"
        ):
            await checker.check_series(123, criteria=SearchCriteria.SPECIAL_EDITION)


class TestTagApplicationExceptionHandling:
    """Tests for exception handling in tag application methods."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_tag_api_connect_error(self) -> None:
        """Should catch ConnectError when tag API fails to connect."""
        import httpx

        from filtarr.config import TagConfig

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
        # Mock get_tags to raise ConnectError
        respx.get("http://localhost:7878/api/v3/tag").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        # Should still return result with has_match = True
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_tag_api_timeout_error(self) -> None:
        """Should catch TimeoutException when tag API times out."""
        import httpx

        from filtarr.config import TagConfig

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
        # Mock get_tags to raise TimeoutException
        respx.get("http://localhost:7878/api/v3/tag").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        # Should still return result with has_match = True
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_tag_api_validation_error(self) -> None:
        """Should catch ValidationError when tag API returns invalid JSON."""
        from filtarr.config import TagConfig

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
        # Mock get_tags to return invalid data (missing required fields)
        respx.get("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[{"invalid_field": "no id or label"}],
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_movie(123, apply_tags=True, dry_run=False)

        # Should still return result with has_match = True
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Validation error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_tag_api_http_500_error(self) -> None:
        """Should catch HTTPStatusError when tag API returns HTTP 500."""
        from filtarr.config import TagConfig

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        # Mock episodes endpoint
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock release endpoint with 4K content
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # Mock get_tags to return HTTP 500
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(500, json={"error": "Internal Server Error"})
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        # Should still return result with has_match = True
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "HTTP 500" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_tag_api_connect_error(self) -> None:
        """Should catch ConnectError when tag API fails to connect."""
        import httpx

        from filtarr.config import TagConfig

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        # Mock episodes endpoint
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock release endpoint with 4K content
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # Mock get_tags to raise ConnectError
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        # Should still return result with has_match = True
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_tag_api_timeout_error(self) -> None:
        """Should catch TimeoutException when tag API times out."""
        import httpx

        from filtarr.config import TagConfig

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        # Mock episodes endpoint
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock release endpoint with 4K content
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # Mock get_tags to raise TimeoutException
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        # Should still return result with has_match = True
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Network error" in result.tag_result.tag_error

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_tag_api_validation_error(self) -> None:
        """Should catch ValidationError when tag API returns invalid JSON."""
        from filtarr.config import TagConfig

        # Mock series info endpoint
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        # Mock episodes endpoint
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock release endpoint with 4K content
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # Mock get_tags to return invalid data (missing required fields)
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[{"invalid_field": "no id or label"}],
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        result = await checker.check_series(123, apply_tags=True, dry_run=False)

        # Should still return result with has_match = True
        assert result.has_match is True
        assert result.tag_result is not None
        assert result.tag_result.tag_error is not None
        assert "Validation error" in result.tag_result.tag_error


class TestSearchResultBackwardCompat:
    """Tests for SearchResult backward compatibility properties."""

    def test_has_4k_property_returns_has_match(self) -> None:
        """Verify has_4k property returns same value as has_match for 4K criteria."""
        from filtarr.criteria import SearchCriteria
        from filtarr.models.common import Quality, Release

        releases = [
            Release(
                guid="1",
                title="Movie.2160p",
                indexer="Test",
                size=1000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
        ]

        # Test with has_match=True
        result_true = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            _criteria=SearchCriteria.FOUR_K,
        )
        assert result_true.has_4k is True
        assert result_true.has_4k == result_true.has_match

        # Test with has_match=False
        result_false = SearchResult(
            item_id=456,
            item_type="movie",
            has_match=False,
            releases=[],
            _criteria=SearchCriteria.FOUR_K,
        )
        assert result_false.has_4k is False
        assert result_false.has_4k == result_false.has_match

    def test_four_k_releases_property_returns_matched(self) -> None:
        """Verify four_k_releases returns 4K releases."""
        from filtarr.criteria import SearchCriteria
        from filtarr.models.common import Quality, Release

        releases = [
            Release(
                guid="1",
                title="Movie.2160p.UHD",
                indexer="Test",
                size=5000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
            Release(
                guid="2",
                title="Movie.1080p.BluRay",
                indexer="Test",
                size=2000,
                quality=Quality(id=7, name="Bluray-1080p"),
            ),
            Release(
                guid="3",
                title="Movie.4K.HDR",
                indexer="Test",
                size=6000,
                quality=Quality(id=31, name="Bluray-2160p"),
            ),
        ]

        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            _criteria=SearchCriteria.FOUR_K,
        )

        four_k = result.four_k_releases
        assert len(four_k) == 2
        assert all(r.is_4k() for r in four_k)
        # Verify the specific 4K releases
        guids = [r.guid for r in four_k]
        assert "1" in guids
        assert "3" in guids
        assert "2" not in guids

    def test_matched_releases_with_none_criteria_uses_4k(self) -> None:
        """Create SearchResult with _criteria=None, verify matched_releases filters for 4K."""
        from filtarr.models.common import Quality, Release

        releases = [
            Release(
                guid="1",
                title="Movie.2160p.UHD",
                indexer="Test",
                size=5000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            ),
            Release(
                guid="2",
                title="Movie.1080p.BluRay",
                indexer="Test",
                size=2000,
                quality=Quality(id=7, name="Bluray-1080p"),
            ),
            Release(
                guid="3",
                title="Movie.720p.WEB",
                indexer="Test",
                size=1000,
                quality=Quality(id=5, name="WEBDL-720p"),
            ),
        ]

        # Create SearchResult with _criteria=None (default backward compat)
        result = SearchResult(
            item_id=123,
            item_type="movie",
            has_match=True,
            releases=releases,
            _criteria=None,  # Explicitly set to None
        )

        # matched_releases should default to 4K filtering when _criteria is None
        matched = result.matched_releases
        assert len(matched) == 1
        assert matched[0].guid == "1"
        assert matched[0].is_4k()


class TestSelectSeasonsDistributedEdgeCases:
    """Tests for select_seasons_to_check DISTRIBUTED edge cases with deduplication."""

    def test_distributed_single_season(self) -> None:
        """Test with only 1 season, verify deduplication works (first=middle=last)."""
        # With a single season, first, middle, and last are all the same
        available = [5]  # Just season 5
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)

        # Should return just that one season, deduplicated
        assert result == [5]
        assert len(result) == 1

    def test_distributed_two_seasons(self) -> None:
        """Test with 2 seasons where middle overlaps with first or last."""
        # With 2 seasons, middle index would be 1 (len//2), which equals the last
        available = [1, 2]
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)

        # Should return both seasons (handled by early return in implementation)
        assert result == [1, 2]
        assert len(result) == 2

    def test_distributed_three_seasons_all_same(self) -> None:
        """Edge case verification with 3 seasons - first, middle, last are all distinct."""
        available = [1, 2, 3]
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)

        # First=1, middle=2 (index 1), last=3 - all distinct
        assert result == [1, 2, 3]
        assert len(result) == 3

    def test_distributed_four_seasons_middle_calculation(self) -> None:
        """Test with 4 seasons to verify middle index calculation."""
        available = [1, 2, 3, 4]
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)

        # First=1, middle=3 (index 2 = 4//2), last=4
        # Result should be sorted and deduplicated
        assert result == [1, 3, 4]
        assert len(result) == 3

    def test_distributed_non_contiguous_seasons(self) -> None:
        """Test with non-contiguous season numbers."""
        # Real-world case: specials (season 0) plus regular seasons
        available = [0, 1, 5, 10]
        result = select_seasons_to_check(available, SamplingStrategy.DISTRIBUTED)

        # sorted: [0, 1, 5, 10]
        # first=0, middle=5 (index 2), last=10
        assert result == [0, 5, 10]
        assert len(result) == 3


class TestCustomCallableMatcher:
    """Tests for custom callable matcher functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_with_custom_callable_matches(self) -> None:
        """Custom callable that returns True for specific title pattern."""
        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        def remux_matcher(release: Release) -> bool:
            return "REMUX" in release.title.upper()

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
                        "title": "Movie.2024.2160p.REMUX.BluRay",
                        "indexer": "Test",
                        "size": 50000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie(123, criteria=remux_matcher, apply_tags=False)

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True
        assert result.item_type == "movie"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_with_custom_callable_no_match(self) -> None:
        """Custom callable that always returns False."""
        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        def never_match(_release: Release) -> bool:
            return False

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
                        "title": "Movie.2024.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie(123, criteria=never_match, apply_tags=False)

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name_with_custom_callable(self) -> None:
        """Test name lookup with custom callable."""
        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        def atmos_matcher(release: Release) -> bool:
            return "ATMOS" in release.title.upper()

        # Mock movie search
        respx.get("http://localhost:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 456, "title": "Inception", "year": 2010}],
            )
        )
        # Mock releases
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Inception.2010.2160p.BluRay.Atmos",
                        "indexer": "Test",
                        "size": 50000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")
        result = await checker.check_movie_by_name(
            "Inception", criteria=atmos_matcher, apply_tags=False
        )

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True
        assert result.item_name == "Inception"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_custom_callable_matches(self) -> None:
        """Custom callable that matches series releases."""
        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        def web_dl_matcher(release: Release) -> bool:
            return "WEB-DL" in release.title.upper() or "WEBDL" in release.title.upper()

        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        # Mock episodes
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock releases with WEB-DL
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01E01.1080p.WEB-DL",
                        "indexer": "Test",
                        "size": 3000,
                        "quality": {"quality": {"id": 7, "name": "WEBDL-1080p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, criteria=web_dl_matcher, apply_tags=False)

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True
        assert result.item_type == "series"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_custom_callable_no_match(self) -> None:
        """Custom callable that never matches."""
        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        def never_match(_release: Release) -> bool:
            return False

        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        # Mock episodes - multiple seasons to verify sampling
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock releases for both seasons
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01E01.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "201"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-201",
                        "title": "Show.S02E01.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, criteria=never_match, apply_tags=False)

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is False
        # Verify sampled episodes were checked
        assert len(result.episodes_checked) >= 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_custom_callable_no_aired_episodes(self) -> None:
        """Series with no aired episodes + custom matcher."""
        from datetime import timedelta

        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        tomorrow = date.today() + timedelta(days=1)

        def any_matcher(_release: Release) -> bool:
            return True  # Would match anything, but there are no aired episodes

        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Upcoming Series", "year": 2025, "seasons": []}
            )
        )
        # Mock episodes - all in future
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": tomorrow.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, criteria=any_matcher, apply_tags=False)

        assert result.has_match is False
        assert result.result_type == ResultType.CUSTOM
        assert result.episodes_checked == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_custom_callable_and_tags(self) -> None:
        """Custom matcher with apply_tags=True on match."""
        from filtarr.config import TagConfig
        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        def hdr_matcher(release: Release) -> bool:
            return "HDR" in release.title.upper()

        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "HDR Series", "year": 2020, "seasons": [], "tags": []},
            )
        )
        # Mock episodes
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock releases with HDR
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01E01.2160p.HDR.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        # Mock tag operations (custom callable falls back to 4K tag names)
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(
            return_value=Response(200, json=[{"id": 1, "label": "4k-available"}])
        )
        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "HDR Series", "year": 2020, "seasons": [], "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )
        result = await checker.check_series(
            123, criteria=hdr_matcher, apply_tags=True, dry_run=False
        )

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True
        assert result.tag_result is not None
        # Custom callable falls back to 4K tag names
        assert result.tag_result.tag_applied == "4k-available"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_by_name_with_custom_callable(self) -> None:
        """Test name lookup with custom callable."""
        from filtarr.criteria import ResultType
        from filtarr.models.common import Release

        def blu_ray_matcher(release: Release) -> bool:
            title = release.title.upper()
            return "BLURAY" in title or "BLU-RAY" in title

        # Mock series search
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 789, "title": "Game of Thrones", "year": 2011, "seasons": []}],
            )
        )
        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/789").mock(
            return_value=Response(
                200, json={"id": 789, "title": "Game of Thrones", "year": 2011, "seasons": []}
            )
        )
        # Mock episodes
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "789"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 789,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2011-04-17",
                        "monitored": True,
                    },
                ],
            )
        )
        # Mock releases with BluRay
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "1001"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-1001",
                        "title": "Game.of.Thrones.S01E01.2160p.BluRay.REMUX",
                        "indexer": "Test",
                        "size": 50000,
                        "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series_by_name(
            "Game of Thrones", criteria=blu_ray_matcher, apply_tags=False
        )

        assert result.result_type == ResultType.CUSTOM
        assert result.has_match is True
        assert result.item_name == "Game of Thrones"


class TestTagCaching:
    """Tests for tag caching behavior in ReleaseChecker."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_radarr_tags_cached_across_multiple_movies(self) -> None:
        """Should only call get_tags once when processing multiple movies."""
        from filtarr.config import TagConfig

        # Track how many times the tag endpoint is called
        tag_call_count = 0

        def tag_response_callback(_request: httpx.Request) -> Response:
            nonlocal tag_call_count
            tag_call_count += 1
            return Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )

        # Mock tag endpoint with callback to track calls
        respx.get("http://localhost:7878/api/v3/tag").mock(side_effect=tag_response_callback)

        # Mock movie info endpoints for two movies
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Movie 2", "year": 2024, "tags": []},
            )
        )

        # Mock release endpoints with 4K content
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie1.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel2",
                        "title": "Movie2.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        # Mock update movie endpoint
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Movie 1", "year": 2024, "tags": [1]},
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Movie 2", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        # Process two movies - tags should be cached after first call
        result1 = await checker.check_movie(123, apply_tags=True, dry_run=False)
        result2 = await checker.check_movie(456, apply_tags=True, dry_run=False)

        # Both should succeed
        assert result1.has_match is True
        assert result1.tag_result is not None
        assert result1.tag_result.tag_applied == "4k-available"

        assert result2.has_match is True
        assert result2.tag_result is not None
        assert result2.tag_result.tag_applied == "4k-available"

        # Key assertion: get_tags should only be called ONCE
        assert tag_call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_sonarr_tags_cached_across_multiple_series(self) -> None:
        """Should only call get_tags once when processing multiple series."""
        from filtarr.config import TagConfig

        # Track how many times the tag endpoint is called
        tag_call_count = 0

        def tag_response_callback(_request: httpx.Request) -> Response:
            nonlocal tag_call_count
            tag_call_count += 1
            return Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )

        # Mock tag endpoint with callback to track calls
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(side_effect=tag_response_callback)

        # Mock series info endpoints for two series
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Series 1", "year": 2020, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200, json={"id": 456, "title": "Series 2", "year": 2021, "seasons": []}
            )
        )

        # Mock episodes endpoints
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 201,
                        "seriesId": 456,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                ],
            )
        )

        # Mock release endpoints with 4K content
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Series1.S01E01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "201"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-201",
                        "title": "Series2.S01E01.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        # Mock update series endpoint
        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Series 1", "year": 2020, "seasons": [], "tags": [1]},
            )
        )
        respx.put("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Series 2", "year": 2021, "seasons": [], "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        # Process two series - tags should be cached after first call
        result1 = await checker.check_series(123, apply_tags=True, dry_run=False)
        result2 = await checker.check_series(456, apply_tags=True, dry_run=False)

        # Both should succeed
        assert result1.has_match is True
        assert result1.tag_result is not None
        assert result1.tag_result.tag_applied == "4k-available"

        assert result2.has_match is True
        assert result2.tag_result is not None
        assert result2.tag_result.tag_applied == "4k-available"

        # Key assertion: get_tags should only be called ONCE
        assert tag_call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_clear_tag_cache_resets_cache(self) -> None:
        """clear_tag_cache should force refetch of tags on next call."""
        from filtarr.config import TagConfig

        # Track how many times the tag endpoint is called
        tag_call_count = 0

        def tag_response_callback(_request: httpx.Request) -> Response:
            nonlocal tag_call_count
            tag_call_count += 1
            return Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )

        # Mock tag endpoint with callback to track calls
        respx.get("http://localhost:7878/api/v3/tag").mock(side_effect=tag_response_callback)

        # Mock movie info endpoints
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Movie 2", "year": 2024, "tags": []},
            )
        )

        # Mock release endpoints
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie1.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel2",
                        "title": "Movie2.2160p.BluRay",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        # Mock update movie endpoint
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Movie 1", "year": 2024, "tags": [1]},
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Movie 2", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        # First movie call - should populate cache
        await checker.check_movie(123, apply_tags=True, dry_run=False)
        assert tag_call_count == 1

        # Clear the cache
        checker.clear_tag_cache()

        # Second movie call - should refetch since cache was cleared
        await checker.check_movie(456, apply_tags=True, dry_run=False)
        assert tag_call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_radarr_and_sonarr_caches_are_separate(self) -> None:
        """Radarr and Sonarr should have separate tag caches."""
        from filtarr.config import TagConfig

        radarr_tag_call_count = 0
        sonarr_tag_call_count = 0

        def radarr_tag_callback(_request: httpx.Request) -> Response:
            nonlocal radarr_tag_call_count
            radarr_tag_call_count += 1
            return Response(200, json=[{"id": 1, "label": "4k-available"}])

        def sonarr_tag_callback(_request: httpx.Request) -> Response:
            nonlocal sonarr_tag_call_count
            sonarr_tag_call_count += 1
            return Response(200, json=[{"id": 10, "label": "4k-available"}])

        # Mock both tag endpoints
        respx.get("http://localhost:7878/api/v3/tag").mock(side_effect=radarr_tag_callback)
        respx.get("http://127.0.0.1:8989/api/v3/tag").mock(side_effect=sonarr_tag_callback)

        # Mock movie endpoints
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
                        "title": "Movie.2160p",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]}
            )
        )

        # Mock series endpoints
        respx.get("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200, json={"id": 456, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 456,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
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
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.put("http://127.0.0.1:8989/api/v3/series/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Test Series", "year": 2020, "seasons": [], "tags": [10]},
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            sonarr_url="http://127.0.0.1:8989",
            sonarr_api_key="test",
            tag_config=tag_config,
        )

        # Check a movie and a series
        await checker.check_movie(123, apply_tags=True, dry_run=False)
        await checker.check_series(456, apply_tags=True, dry_run=False)

        # Both endpoints should be called once (separate caches)
        assert radarr_tag_call_count == 1
        assert sonarr_tag_call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_cache_updated_when_tag_created(self) -> None:
        """When a new tag is created, it should be added to the cache."""
        from filtarr.config import TagConfig

        tag_call_count = 0

        def tag_response_callback(_request: httpx.Request) -> Response:
            nonlocal tag_call_count
            tag_call_count += 1
            # Return empty tags on first call (tag doesn't exist yet)
            return Response(200, json=[])

        # Mock tag endpoint
        respx.get("http://localhost:7878/api/v3/tag").mock(side_effect=tag_response_callback)

        # Mock create tag endpoint
        respx.post("http://localhost:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-available"})
        )

        # Mock movie endpoints for two movies
        respx.get("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Movie 1", "year": 2024, "tags": []},
            )
        )
        respx.get("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(
                200,
                json={"id": 456, "title": "Movie 2", "year": 2024, "tags": []},
            )
        )

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel1",
                        "title": "Movie1.2160p",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel2",
                        "title": "Movie2.2160p",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        respx.put("http://localhost:7878/api/v3/movie/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Movie 1", "year": 2024, "tags": [1]}
            )
        )
        respx.put("http://localhost:7878/api/v3/movie/456").mock(
            return_value=Response(
                200, json={"id": 456, "title": "Movie 2", "year": 2024, "tags": [1]}
            )
        )

        tag_config = TagConfig(_available="4k-available", _unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test",
            tag_config=tag_config,
        )

        # First movie: tag doesn't exist, gets created
        result1 = await checker.check_movie(123, apply_tags=True, dry_run=False)
        assert result1.tag_result is not None
        assert result1.tag_result.tag_created is True

        # Second movie: should use cached tag (no new tag creation)
        result2 = await checker.check_movie(456, apply_tags=True, dry_run=False)
        assert result2.tag_result is not None
        assert result2.tag_result.tag_created is False  # Tag was found in cache

        # Tags should only be fetched once
        assert tag_call_count == 1

    def test_clear_tag_cache_on_new_instance(self) -> None:
        """New ReleaseChecker instance should have empty cache."""
        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        # Cache should be None on new instance (managed by tagger)
        assert checker._tagger._tag_cache is None

    def test_clear_tag_cache_method(self) -> None:
        """clear_tag_cache should reset cache to None."""
        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test")

        # Manually set some cache data (on the tagger)
        checker._tagger._tag_cache = {"radarr": []}

        # Clear the cache
        checker.clear_tag_cache()

        # Cache should be None
        assert checker._tagger._tag_cache is None


class TestClientInjection:
    """Tests for pre-created client injection in ReleaseChecker.

    Task 3.1: Accept Pre-Created Clients in ReleaseChecker
    - Injected clients should be used when provided
    - Backward compatibility should be maintained
    - Injected clients should NOT be closed on __aexit__
    """

    @pytest.mark.asyncio
    async def test_injected_radarr_client_is_used(self) -> None:
        """Should use injected radarr_client when provided."""
        from unittest.mock import AsyncMock, MagicMock

        from filtarr.clients.radarr import RadarrClient
        from filtarr.models.common import Quality, Release
        from filtarr.models.radarr import Movie

        # Create a mock client
        mock_client = MagicMock(spec=RadarrClient)
        mock_client.get_movie = AsyncMock(return_value=Movie(id=123, title="Test Movie", year=2024))
        mock_client.get_movie_releases = AsyncMock(
            return_value=[
                Release(
                    guid="rel-1",
                    title="Movie.2160p.UHD",
                    indexer="Test",
                    size=5000,
                    quality=Quality(id=31, name="Bluray-2160p"),
                )
            ]
        )

        # Create checker with injected client
        checker = ReleaseChecker(radarr_client=mock_client)

        # The injected client should be stored
        assert checker._radarr_client is mock_client

        # Perform a check - it should use the injected client
        result = await checker.check_movie(123, apply_tags=False)

        # Verify the injected client was used
        mock_client.get_movie.assert_called_once_with(123)
        mock_client.get_movie_releases.assert_called_once_with(123)
        assert result.has_match is True
        assert result.item_id == 123

    @pytest.mark.asyncio
    async def test_injected_sonarr_client_is_used(self) -> None:
        """Should use injected sonarr_client when provided."""
        from datetime import date
        from unittest.mock import AsyncMock, MagicMock

        from filtarr.clients.sonarr import SonarrClient
        from filtarr.models.common import Quality, Release
        from filtarr.models.sonarr import Episode, Series

        # Create a mock client
        mock_client = MagicMock(spec=SonarrClient)
        mock_client.get_series = AsyncMock(
            return_value=Series(id=456, title="Test Series", year=2020, seasons=[])
        )
        mock_client.get_episodes = AsyncMock(
            return_value=[
                Episode(
                    id=101,
                    series_id=456,
                    season_number=1,
                    episode_number=1,
                    air_date=date(2020, 1, 1),
                    monitored=True,
                )
            ]
        )
        mock_client.get_episode_releases = AsyncMock(
            return_value=[
                Release(
                    guid="rel-1",
                    title="Show.S01.2160p",
                    indexer="Test",
                    size=3000,
                    quality=Quality(id=19, name="WEBDL-2160p"),
                )
            ]
        )

        # Create checker with injected client
        checker = ReleaseChecker(sonarr_client=mock_client)

        # The injected client should be stored
        assert checker._sonarr_client is mock_client

        # Perform a check - it should use the injected client
        result = await checker.check_series(456, apply_tags=False)

        # Verify the injected client was used
        mock_client.get_series.assert_called_once_with(456)
        mock_client.get_episodes.assert_called_once_with(456)
        assert result.has_match is True
        assert result.item_id == 456

    @pytest.mark.asyncio
    async def test_backward_compatibility_url_api_key_still_works(self) -> None:
        """Should maintain backward compatibility when using URL + API key."""
        # This uses respx to mock HTTP calls, same as existing tests
        import respx
        from httpx import Response

        with respx.mock:
            respx.get("http://localhost:7878/api/v3/movie/123").mock(
                return_value=Response(200, json={"id": 123, "title": "Test Movie", "year": 2024})
            )
            respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
                return_value=Response(
                    200,
                    json=[
                        {
                            "guid": "rel-1",
                            "title": "Movie.2160p.UHD",
                            "indexer": "Test",
                            "size": 5000,
                            "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}},
                        }
                    ],
                )
            )

            # Create checker with URL + API key (backward compatible way)
            checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test-key")

            # Clients should not be stored initially (created on demand)
            assert checker._radarr_client is None

            # Perform a check
            result = await checker.check_movie(123, apply_tags=False)

            assert result.has_match is True
            assert result.item_id == 123

    @pytest.mark.asyncio
    async def test_injected_clients_not_closed_on_aexit(self) -> None:
        """Injected clients should NOT be closed on __aexit__ (caller manages lifecycle)."""
        from unittest.mock import AsyncMock, MagicMock

        from filtarr.clients.radarr import RadarrClient
        from filtarr.clients.sonarr import SonarrClient

        # Create mock clients with tracked __aexit__
        mock_radarr = MagicMock(spec=RadarrClient)
        mock_radarr.__aexit__ = AsyncMock()

        mock_sonarr = MagicMock(spec=SonarrClient)
        mock_sonarr.__aexit__ = AsyncMock()

        # Create checker with injected clients
        checker = ReleaseChecker(radarr_client=mock_radarr, sonarr_client=mock_sonarr)

        # Use as context manager
        async with checker:
            # Clients should be available
            assert checker._radarr_client is mock_radarr
            assert checker._sonarr_client is mock_sonarr

        # After exiting context, __aexit__ should NOT have been called on injected clients
        mock_radarr.__aexit__.assert_not_called()
        mock_sonarr.__aexit__.assert_not_called()

        # Injected clients should still be stored (not None'd out)
        assert checker._radarr_client is mock_radarr
        assert checker._sonarr_client is mock_sonarr

    @pytest.mark.asyncio
    async def test_internally_created_clients_are_closed_on_aexit(self) -> None:
        """Internally-created clients should be closed on __aexit__."""
        from unittest.mock import AsyncMock, patch

        from filtarr.clients.radarr import RadarrClient

        # Create checker with URL + API key (will create client internally)
        checker = ReleaseChecker(radarr_url="http://localhost:7878", radarr_api_key="test-key")

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock) as exit_mock,
        ):
            enter.return_value = None

            async with checker:
                # Client should be created
                assert checker._radarr_client is not None

            # __aexit__ SHOULD have been called for internally-created client
            exit_mock.assert_called_once()

            # Client should be None'd out after exiting
            assert checker._radarr_client is None

    @pytest.mark.asyncio
    async def test_mixed_injection_and_config(self) -> None:
        """Should support mixed mode: injected client + URL config for other."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from filtarr.clients.radarr import RadarrClient
        from filtarr.clients.sonarr import SonarrClient

        # Create mock Radarr client (injected)
        mock_radarr = MagicMock(spec=RadarrClient)
        mock_radarr.__aexit__ = AsyncMock()

        # Create checker with injected Radarr + Sonarr URL config
        checker = ReleaseChecker(
            radarr_client=mock_radarr,
            sonarr_url="http://localhost:8989",
            sonarr_api_key="test-key",
        )

        with (
            patch.object(SonarrClient, "__aenter__", new_callable=AsyncMock) as sonarr_enter,
            patch.object(SonarrClient, "__aexit__", new_callable=AsyncMock) as sonarr_exit,
        ):
            sonarr_enter.return_value = None

            async with checker:
                # Radarr should use injected client
                assert checker._radarr_client is mock_radarr
                # Sonarr should be created internally
                assert checker._sonarr_client is not None

            # Radarr (injected) should NOT have __aexit__ called
            mock_radarr.__aexit__.assert_not_called()
            # Sonarr (internally created) SHOULD have __aexit__ called
            sonarr_exit.assert_called_once()

    def test_injected_client_takes_precedence_over_url_config(self) -> None:
        """Injected client should take precedence over URL + API key config."""
        from unittest.mock import MagicMock

        from filtarr.clients.radarr import RadarrClient

        mock_client = MagicMock(spec=RadarrClient)

        # Provide BOTH injected client AND URL config
        checker = ReleaseChecker(
            radarr_client=mock_client,
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        # Injected client should be used
        assert checker._radarr_client is mock_client

    @pytest.mark.asyncio
    async def test_check_movie_with_injected_client_in_context(self) -> None:
        """Injected client should work correctly when used within async context."""
        from unittest.mock import AsyncMock, MagicMock

        from filtarr.clients.radarr import RadarrClient
        from filtarr.models.common import Quality, Release
        from filtarr.models.radarr import Movie

        mock_client = MagicMock(spec=RadarrClient)
        mock_client.get_movie = AsyncMock(return_value=Movie(id=123, title="Test Movie", year=2024))
        mock_client.get_movie_releases = AsyncMock(
            return_value=[
                Release(
                    guid="rel-1",
                    title="Movie.2160p.UHD",
                    indexer="Test",
                    size=5000,
                    quality=Quality(id=31, name="Bluray-2160p"),
                )
            ]
        )

        checker = ReleaseChecker(radarr_client=mock_client)

        # Use as context manager
        async with checker:
            result = await checker.check_movie(123, apply_tags=False)

            assert result.has_match is True
            mock_client.get_movie.assert_called_once()

    def test_injected_client_sets_in_context_flag_appropriately(self) -> None:
        """With injected client, _in_context should still be managed correctly."""
        from unittest.mock import MagicMock

        from filtarr.clients.radarr import RadarrClient

        mock_client = MagicMock(spec=RadarrClient)
        checker = ReleaseChecker(radarr_client=mock_client)

        # Before context, _in_context should be False
        assert checker._in_context is False

    @pytest.mark.asyncio
    async def test_raises_error_when_neither_injected_nor_configured_for_radarr(
        self,
    ) -> None:
        """Should raise ValueError when Radarr is neither injected nor configured."""
        checker = ReleaseChecker()

        with pytest.raises(ValueError, match="Radarr is not configured"):
            await checker.check_movie(123)

    @pytest.mark.asyncio
    async def test_raises_error_when_neither_injected_nor_configured_for_sonarr(
        self,
    ) -> None:
        """Should raise ValueError when Sonarr is neither injected nor configured."""
        checker = ReleaseChecker()

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            await checker.check_series(456)


class TestParallelEpisodeChecks:
    """Tests for parallel episode release fetching.

    These tests verify that episode release checks run concurrently using
    asyncio.gather while maintaining correct short-circuit behavior when
    a match is found.
    """

    @respx.mock
    @pytest.mark.asyncio
    async def test_multiple_episode_checks_run_concurrently(self) -> None:
        """Multiple episode checks should run in parallel, not sequentially.

        This test verifies that when checking multiple seasons, all episode
        release requests are made concurrently, not one after another.
        We measure the total time and verify it's close to the slowest single
        request (parallel) rather than the sum of all requests (sequential).
        """
        import asyncio
        import time

        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        # Mock episodes for 3 seasons
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 301,
                        "seriesId": 123,
                        "seasonNumber": 3,
                        "episodeNumber": 1,
                        "airDate": "2022-01-01",
                        "monitored": True,
                    },
                ],
            )
        )

        # Track request timing to verify parallelism
        request_times: list[tuple[int, float, float]] = []  # (ep_id, start, end)
        delay_per_request = 0.1  # 100ms per request

        async def delayed_response(request: httpx.Request) -> Response:
            """Simulate network latency for each request."""
            ep_id = int(request.url.params["episodeId"])
            start = time.time()
            await asyncio.sleep(delay_per_request)
            end = time.time()
            request_times.append((ep_id, start, end))
            return Response(
                200,
                json=[
                    {
                        "guid": f"rel-{ep_id}",
                        "title": "Show.S0X.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )

        # Mock release endpoints with delay
        for ep_id in [101, 201, 301]:
            respx.get(
                "http://127.0.0.1:8989/api/v3/release", params={"episodeId": str(ep_id)}
            ).mock(side_effect=delayed_response)

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        start_time = time.time()
        result = await checker.check_series(123, strategy=SamplingStrategy.ALL, apply_tags=False)
        total_time = time.time() - start_time

        assert result.has_match is False
        assert len(result.seasons_checked) == 3

        # Verify parallel execution: total time should be close to single request time
        # If sequential, it would take 3 * 0.1 = 0.3s
        # If parallel, it should take ~0.1s (plus overhead)
        # We allow 50% tolerance for parallel (0.1 * 1.5 = 0.15s)
        # and require it to be faster than sequential (0.3s)
        assert total_time < delay_per_request * len(request_times), (
            f"Requests appear sequential: took {total_time:.3f}s for "
            f"{len(request_times)} requests, expected < {delay_per_request * len(request_times):.3f}s"
        )

        # Verify all requests were made
        assert len(request_times) == 3
        ep_ids = [rt[0] for rt in request_times]
        assert set(ep_ids) == {101, 201, 301}

    @respx.mock
    @pytest.mark.asyncio
    async def test_short_circuit_on_first_match_with_parallel_fetch(self) -> None:
        """Short-circuit should still work when a match is found during parallel fetch.

        Even with parallel fetching, if any season has a match, the result
        should indicate has_match=True and include the matching releases.
        """
        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        # Mock episodes for 3 seasons
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 301,
                        "seriesId": 123,
                        "seasonNumber": 3,
                        "episodeNumber": 1,
                        "airDate": "2022-01-01",
                        "monitored": True,
                    },
                ],
            )
        )

        # Season 1: No 4K
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        # Season 2: Has 4K!
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "201"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-201-4k",
                        "title": "Show.S02.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        # Season 3: No 4K
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "301"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-301",
                        "title": "Show.S03.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, strategy=SamplingStrategy.ALL, apply_tags=False)

        # Should find the 4K match
        assert result.has_match is True
        # All seasons should be checked since fetches happen in parallel
        assert len(result.seasons_checked) == 3
        # Should have releases from all seasons
        assert len(result.releases) == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_error_in_one_request_does_not_break_others(self) -> None:
        """Error in one episode release request should not prevent other checks.

        When fetching releases in parallel, if one request fails, the others
        should still complete successfully and the results should be available.
        """
        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        # Mock episodes for 3 seasons
        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 101,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "airDate": "2020-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 201,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "airDate": "2021-01-01",
                        "monitored": True,
                    },
                    {
                        "id": 301,
                        "seriesId": 123,
                        "seasonNumber": 3,
                        "episodeNumber": 1,
                        "airDate": "2022-01-01",
                        "monitored": True,
                    },
                ],
            )
        )

        # Season 1: Success (no 4K)
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "101"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-101",
                        "title": "Show.S01.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        # Season 2: Error (HTTP 500)
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "201"}).mock(
            return_value=Response(500, json={"error": "Internal Server Error"})
        )

        # Season 3: Success with 4K
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"episodeId": "301"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "rel-301-4k",
                        "title": "Show.S03.2160p.WEB-DL",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")
        result = await checker.check_series(123, strategy=SamplingStrategy.ALL, apply_tags=False)

        # Should still find the 4K match from season 3
        assert result.has_match is True
        # Successful seasons should be checked
        assert 1 in result.seasons_checked
        assert 3 in result.seasons_checked
        # Should have releases from successful requests
        assert len(result.releases) >= 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_timing_verifies_parallel_not_sequential_execution(self) -> None:
        """Verify requests execute in parallel using timing measurements.

        This is a more rigorous timing test that explicitly measures whether
        requests overlap in time (parallel) vs execute one after another (sequential).
        """
        import asyncio
        import time

        # Mock series info
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        # Mock 5 seasons for more pronounced timing difference
        episodes = [
            {
                "id": 100 + i,
                "seriesId": 123,
                "seasonNumber": i,
                "episodeNumber": 1,
                "airDate": f"202{i}-01-01",
                "monitored": True,
            }
            for i in range(1, 6)
        ]

        respx.get("http://127.0.0.1:8989/api/v3/episode", params={"seriesId": "123"}).mock(
            return_value=Response(200, json=episodes)
        )

        request_events: list[tuple[str, float, int]] = []  # (event, time, ep_id)
        delay = 0.05  # 50ms per request

        async def timed_response(request: httpx.Request) -> Response:
            ep_id = int(request.url.params["episodeId"])
            request_events.append(("start", time.time(), ep_id))
            await asyncio.sleep(delay)
            request_events.append(("end", time.time(), ep_id))
            return Response(
                200,
                json=[
                    {
                        "guid": f"rel-{ep_id}",
                        "title": "Show.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )

        for ep_id in [101, 102, 103, 104, 105]:
            respx.get(
                "http://127.0.0.1:8989/api/v3/release", params={"episodeId": str(ep_id)}
            ).mock(side_effect=timed_response)

        checker = ReleaseChecker(sonarr_url="http://127.0.0.1:8989", sonarr_api_key="test")

        start_time = time.time()
        result = await checker.check_series(123, strategy=SamplingStrategy.ALL, apply_tags=False)
        total_time = time.time() - start_time

        assert result.has_match is False
        assert len(result.seasons_checked) == 5

        # Calculate overlap to verify parallelism
        # With parallel execution: all requests start at roughly the same time
        # With sequential execution: each starts after the previous ends
        start_events = [(t, ep) for event, t, ep in request_events if event == "start"]

        # All start times should be within a small window for parallel execution
        start_times = [t for t, _ in start_events]
        start_spread = max(start_times) - min(start_times)

        # For parallel execution, spread should be very small (< delay)
        # For sequential execution, spread would be >= (n-1) * delay
        assert start_spread < delay * 2, (
            f"Requests not starting in parallel: spread is {start_spread:.3f}s, "
            f"expected < {delay * 2:.3f}s"
        )

        # Total time should be close to single request time
        # Sequential would be 5 * 0.05 = 0.25s
        # Parallel should be ~0.05s + overhead
        assert total_time < delay * len(start_events), (
            f"Total time {total_time:.3f}s suggests sequential execution, "
            f"expected < {delay * len(start_events):.3f}s for parallel"
        )
