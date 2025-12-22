"""Tests for FourKChecker and sampling strategies."""

from datetime import date, timedelta

import pytest
import respx
from httpx import Response

from findarr.checker import (
    FourKChecker,
    FourKResult,
    SamplingStrategy,
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


class TestFourKResult:
    """Tests for FourKResult dataclass."""

    def test_four_k_releases_property(self) -> None:
        """Should filter to only 4K releases."""
        from findarr.models.common import Quality, Release

        releases = [
            Release(guid="1", title="Movie.2160p", indexer="Test", size=1000,
                   quality=Quality(id=19, name="WEBDL-2160p")),
            Release(guid="2", title="Movie.1080p", indexer="Test", size=500,
                   quality=Quality(id=7, name="Bluray-1080p")),
            Release(guid="3", title="Movie.4K.HDR", indexer="Test", size=1500,
                   quality=Quality(id=31, name="Bluray-2160p")),
        ]

        result = FourKResult(
            item_id=123,
            item_type="movie",
            has_4k=True,
            releases=releases,
        )

        four_k = result.four_k_releases
        assert len(four_k) == 2
        assert all(r.is_4k() for r in four_k)


class TestCheckSeriesWithSampling:
    """Integration tests for check_series with sampling strategies."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_recent_strategy(self) -> None:
        """Should check latest episodes from recent seasons."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Mock episodes endpoint
        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    # Season 1 episodes
                    {"id": 101, "seriesId": 123, "seasonNumber": 1, "episodeNumber": 1,
                     "airDate": "2020-01-01", "monitored": True},
                    {"id": 102, "seriesId": 123, "seasonNumber": 1, "episodeNumber": 2,
                     "airDate": "2020-01-08", "monitored": True},
                    # Season 2 episodes
                    {"id": 201, "seriesId": 123, "seasonNumber": 2, "episodeNumber": 1,
                     "airDate": "2021-01-01", "monitored": True},
                    # Season 3 episodes
                    {"id": 301, "seriesId": 123, "seasonNumber": 3, "episodeNumber": 1,
                     "airDate": "2022-01-01", "monitored": True},
                    # Season 4 episodes
                    {"id": 401, "seriesId": 123, "seasonNumber": 4, "episodeNumber": 1,
                     "airDate": "2023-01-01", "monitored": True},
                    # Season 5 episodes (most recent)
                    {"id": 501, "seriesId": 123, "seasonNumber": 5, "episodeNumber": 1,
                     "airDate": yesterday.isoformat(), "monitored": True},
                ],
            )
        )

        # Mock release endpoints - no 4K releases
        for ep_id in [301, 401, 501]:  # Latest 3 seasons
            respx.get(
                "http://sonarr:8989/api/v3/release", params={"episodeId": str(ep_id)}
            ).mock(
                return_value=Response(
                    200,
                    json=[
                        {"guid": f"rel-{ep_id}", "title": "Show.S0X.1080p",
                         "indexer": "Test", "size": 1000,
                         "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}}}
                    ],
                )
            )

        checker = FourKChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        result = await checker.check_series(123, strategy=SamplingStrategy.RECENT, seasons_to_check=3)

        assert result.has_4k is False
        assert result.strategy_used == SamplingStrategy.RECENT
        assert sorted(result.seasons_checked) == [3, 4, 5]
        assert len(result.episodes_checked) == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_short_circuits_on_4k(self) -> None:
        """Should stop checking after finding 4K."""
        today = date.today()
        yesterday = today - timedelta(days=1)

        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {"id": 101, "seriesId": 123, "seasonNumber": 1, "episodeNumber": 1,
                     "airDate": "2020-01-01", "monitored": True},
                    {"id": 201, "seriesId": 123, "seasonNumber": 2, "episodeNumber": 1,
                     "airDate": "2021-01-01", "monitored": True},
                    {"id": 301, "seriesId": 123, "seasonNumber": 3, "episodeNumber": 1,
                     "airDate": yesterday.isoformat(), "monitored": True},
                ],
            )
        )

        # First season checked (season 1) - no 4K
        respx.get(
            "http://sonarr:8989/api/v3/release", params={"episodeId": "101"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {"guid": "rel-101", "title": "Show.S01.1080p",
                     "indexer": "Test", "size": 1000,
                     "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}}}
                ],
            )
        )

        # Second season (season 2) - has 4K!
        respx.get(
            "http://sonarr:8989/api/v3/release", params={"episodeId": "201"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {"guid": "rel-201-4k", "title": "Show.S02.2160p.WEB-DL",
                     "indexer": "Test", "size": 5000,
                     "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}}}
                ],
            )
        )

        # Season 3 should NOT be called due to short-circuit
        # (we don't mock it - if called, test would fail)

        checker = FourKChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        result = await checker.check_series(123, strategy=SamplingStrategy.ALL)

        assert result.has_4k is True
        # Should have stopped after finding 4K in season 2
        assert result.seasons_checked == [1, 2]
        assert len(result.episodes_checked) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_no_aired_episodes(self) -> None:
        """Should return empty result when no episodes have aired."""
        tomorrow = date.today() + timedelta(days=1)

        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {"id": 101, "seriesId": 123, "seasonNumber": 1, "episodeNumber": 1,
                     "airDate": tomorrow.isoformat(), "monitored": True},
                ],
            )
        )

        checker = FourKChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        result = await checker.check_series(123)

        assert result.has_4k is False
        assert result.episodes_checked == []
        assert result.seasons_checked == []
        assert result.strategy_used == SamplingStrategy.RECENT

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_series_with_distributed_strategy(self) -> None:
        """Should check first, middle, and last seasons with DISTRIBUTED."""
        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {"id": 101, "seriesId": 123, "seasonNumber": 1, "episodeNumber": 1,
                     "airDate": "2020-01-01", "monitored": True},
                    {"id": 201, "seriesId": 123, "seasonNumber": 2, "episodeNumber": 1,
                     "airDate": "2021-01-01", "monitored": True},
                    {"id": 301, "seriesId": 123, "seasonNumber": 3, "episodeNumber": 1,
                     "airDate": "2022-01-01", "monitored": True},
                    {"id": 401, "seriesId": 123, "seasonNumber": 4, "episodeNumber": 1,
                     "airDate": "2023-01-01", "monitored": True},
                    {"id": 501, "seriesId": 123, "seasonNumber": 5, "episodeNumber": 1,
                     "airDate": "2024-01-01", "monitored": True},
                ],
            )
        )

        # Mock releases for seasons 1, 3, 5 (first, middle, last)
        for ep_id in [101, 301, 501]:
            respx.get(
                "http://sonarr:8989/api/v3/release", params={"episodeId": str(ep_id)}
            ).mock(
                return_value=Response(200, json=[])
            )

        checker = FourKChecker(sonarr_url="http://sonarr:8989", sonarr_api_key="test")
        result = await checker.check_series(123, strategy=SamplingStrategy.DISTRIBUTED)

        assert result.has_4k is False
        assert result.strategy_used == SamplingStrategy.DISTRIBUTED
        assert sorted(result.seasons_checked) == [1, 3, 5]

    @pytest.mark.asyncio
    async def test_check_series_raises_when_not_configured(self) -> None:
        """Should raise ValueError when Sonarr not configured."""
        checker = FourKChecker()  # No Sonarr config

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            await checker.check_series(123)

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_movie_still_works(self) -> None:
        """Verify check_movie still functions correctly."""
        respx.get(
            "http://radarr:7878/api/v3/release", params={"movieId": "456"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {"guid": "movie-rel", "title": "Movie.2024.2160p.UHD",
                     "indexer": "Test", "size": 15000,
                     "quality": {"quality": {"id": 31, "name": "Bluray-2160p"}}}
                ],
            )
        )

        checker = FourKChecker(radarr_url="http://radarr:7878", radarr_api_key="test")
        result = await checker.check_movie(456)

        assert result.has_4k is True
        assert result.item_type == "movie"
        assert result.item_id == 456

    @pytest.mark.asyncio
    async def test_check_movie_raises_when_not_configured(self) -> None:
        """Should raise ValueError when Radarr not configured."""
        checker = FourKChecker()  # No Radarr config

        with pytest.raises(ValueError, match="Radarr is not configured"):
            await checker.check_movie(456)
