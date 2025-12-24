"""Tests for ReleaseChecker and sampling strategies."""

from datetime import date, timedelta

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


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_matched_releases_property(self) -> None:
        """Should filter to only 4K releases."""
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
            item_type="movie",
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
        respx.get("http://sonarr:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        # Mock episodes endpoint
        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}).mock(
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
            respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": str(ep_id)}).mock(
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

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
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
        respx.get("http://sonarr:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}).mock(
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
        respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": "101"}).mock(
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
        respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": "201"}).mock(
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

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
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
        respx.get("http://sonarr:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}).mock(
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

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
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
        respx.get("http://sonarr:8989/api/v3/series/123").mock(
            return_value=Response(
                200, json={"id": 123, "title": "Test Series", "year": 2020, "seasons": []}
            )
        )

        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}).mock(
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
            respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": str(ep_id)}).mock(
                return_value=Response(200, json=[])
            )

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
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
        respx.get("http://radarr:7878/api/v3/movie/456").mock(
            return_value=Response(200, json={"id": 456, "title": "Test Movie", "year": 2024})
        )

        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "456"}).mock(
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

        checker = ReleaseChecker(radarr_url="http://radarr:7878", radarr_api_key="test")
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
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "The Matrix", "year": 1999},
                    {"id": 2, "title": "The Matrix Reloaded", "year": 2003},
                ],
            )
        )

        checker = ReleaseChecker(radarr_url="http://radarr:7878", radarr_api_key="test")
        results = await checker.search_movies("Matrix")

        assert len(results) == 2
        assert results[0] == (1, "The Matrix", 1999)
        assert results[1] == (2, "The Matrix Reloaded", 2003)

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_series_returns_tuples(self) -> None:
        """Should return list of (id, title, year) tuples."""
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "title": "Breaking Bad", "year": 2008, "seasons": []},
                ],
            )
        )

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        results = await checker.search_series("Breaking")

        assert len(results) == 1
        assert results[0] == (1, "Breaking Bad", 2008)

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name(self) -> None:
        """Should check movie by name."""
        # Mock search
        respx.get("http://radarr:7878/api/v3/movie").mock(
            return_value=Response(
                200,
                json=[{"id": 123, "title": "The Matrix", "year": 1999}],
            )
        )
        # Mock releases
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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

        checker = ReleaseChecker(radarr_url="http://radarr:7878", radarr_api_key="test")
        result = await checker.check_movie_by_name("The Matrix", apply_tags=False)

        assert result.has_match is True
        assert result.item_id == 123
        assert result.item_type == "movie"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_by_name_not_found(self) -> None:
        """Should raise ValueError when movie not found."""
        respx.get("http://radarr:7878/api/v3/movie").mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(radarr_url="http://radarr:7878", radarr_api_key="test")

        with pytest.raises(ValueError, match="Movie not found"):
            await checker.check_movie_by_name("Nonexistent Movie")

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_by_name(self) -> None:
        """Should check series by name."""
        # Mock search
        respx.get("http://sonarr:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[{"id": 456, "title": "Breaking Bad", "year": 2008, "seasons": []}],
            )
        )
        # Mock series info
        respx.get("http://sonarr:8989/api/v3/series/456").mock(
            return_value=Response(
                200, json={"id": 456, "title": "Breaking Bad", "year": 2008, "seasons": []}
            )
        )
        # Mock episodes
        respx.get("http://sonarr:8989/api/v3/episode", params={"seriesId": "456"}).mock(
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
        respx.get("http://sonarr:8989/api/v3/release", params={"episodeId": "1001"}).mock(
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

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        result = await checker.check_series_by_name("Breaking Bad", apply_tags=False)

        assert result.has_match is True
        assert result.item_id == 456
        assert result.item_type == "series"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_by_name_not_found(self) -> None:
        """Should raise ValueError when series not found."""
        respx.get("http://sonarr:8989/api/v3/series").mock(return_value=Response(200, json=[]))

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")

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
        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        # Mock releases
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        respx.get("http://radarr:7878/api/v3/tag").mock(return_value=Response(200, json=[]))
        # Mock create_tag
        respx.post("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(201, json={"id": 1, "label": "4k-available"})
        )
        # Mock update_movie
        respx.put("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        respx.get("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )
        # Mock update_movie
        respx.put("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [2]},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        respx.get("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )
        respx.put("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        # No 4K releases
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        respx.get("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[
                    {"id": 1, "label": "4k-available"},
                    {"id": 2, "label": "4k-unavailable"},
                ],
            )
        )
        respx.put("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [2]},
            )
        )

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        respx.get("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(500, json={"error": "Server error"})
        )

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        respx.get("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": []},
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        respx.get("http://radarr:7878/api/v3/tag").mock(
            return_value=Response(
                200,
                json=[{"id": 1, "label": "4K-Available"}],  # Different case
            )
        )
        respx.put("http://radarr:7878/api/v3/movie/123").mock(
            return_value=Response(
                200,
                json={"id": 123, "title": "Test Movie", "year": 2024, "tags": [1]},
            )
        )

        tag_config = TagConfig(available="4k-available", unavailable="4k-unavailable")
        checker = ReleaseChecker(
            radarr_url="http://radarr:7878",
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

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="DIRECTORS_CUT criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.DIRECTORS_CUT)

    @pytest.mark.asyncio
    async def test_check_series_rejects_extended(self) -> None:
        """check_series should raise ValueError for EXTENDED criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="EXTENDED criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.EXTENDED)

    @pytest.mark.asyncio
    async def test_check_series_rejects_remaster(self) -> None:
        """check_series should raise ValueError for REMASTER criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="REMASTER criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.REMASTER)

    @pytest.mark.asyncio
    async def test_check_series_rejects_imax(self) -> None:
        """check_series should raise ValueError for IMAX criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        with pytest.raises(ValueError, match="IMAX criteria is only applicable to movies"):
            await checker.check_series(123, criteria=SearchCriteria.IMAX)

    @pytest.mark.asyncio
    async def test_check_series_rejects_special_edition(self) -> None:
        """check_series should raise ValueError for SPECIAL_EDITION criteria."""
        from filtarr.criteria import SearchCriteria

        checker = ReleaseChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        with pytest.raises(
            ValueError, match="SPECIAL_EDITION criteria is only applicable to movies"
        ):
            await checker.check_series(123, criteria=SearchCriteria.SPECIAL_EDITION)
