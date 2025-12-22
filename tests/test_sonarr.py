"""Tests for Sonarr-specific functionality."""

from datetime import date, timedelta

import pytest
import respx
from httpx import Response

from findarr.clients.sonarr import SonarrClient


class TestGetSeries:
    """Tests for get_series method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_parses_response(self) -> None:
        """Should parse series with seasons from API response."""
        respx.get("http://sonarr:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Show",
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
                },
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            series = await client.get_series(123)

        assert series.id == 123
        assert series.title == "Test Show"
        assert series.year == 2024
        assert len(series.seasons) == 2
        assert series.seasons[0].season_number == 1
        assert series.seasons[0].monitored is True
        assert series.seasons[0].episode_count == 10
        assert series.seasons[1].season_number == 2
        assert series.seasons[1].monitored is False


class TestGetEpisodes:
    """Tests for get_episodes method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_episodes_parses_response(self) -> None:
        """Should parse episode list from API response."""
        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "title": "Pilot",
                        "airDate": "2024-01-15",
                        "airDateUtc": "2024-01-15T20:00:00Z",
                        "hasFile": True,
                        "monitored": True,
                    },
                    {
                        "id": 1002,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "title": "Second Episode",
                        "airDate": "2024-01-22",
                        "airDateUtc": "2024-01-22T20:00:00Z",
                        "hasFile": False,
                        "monitored": True,
                    },
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            episodes = await client.get_episodes(123)

        assert len(episodes) == 2
        assert episodes[0].id == 1001
        assert episodes[0].series_id == 123
        assert episodes[0].season_number == 1
        assert episodes[0].episode_number == 1
        assert episodes[0].title == "Pilot"
        assert episodes[0].air_date == date(2024, 1, 15)
        assert episodes[0].has_file is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_episodes_with_season_filter(self) -> None:
        """Should include seasonNumber in query params when specified."""
        respx.get(
            "http://sonarr:8989/api/v3/episode",
            params={"seriesId": "123", "seasonNumber": "2"},
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 2001,
                        "seriesId": 123,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "title": "Season 2 Premiere",
                        "airDate": "2024-09-01",
                        "monitored": True,
                    }
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            episodes = await client.get_episodes(123, season_number=2)

        assert len(episodes) == 1
        assert episodes[0].season_number == 2


class TestGetEpisodeReleases:
    """Tests for get_episode_releases method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_episode_releases_parses_response(self) -> None:
        """Should parse releases for a specific episode."""
        respx.get(
            "http://sonarr:8989/api/v3/release", params={"episodeId": "1001"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "release-abc",
                        "title": "Show.S01E01.2160p.WEB-DL.x265",
                        "indexer": "TestIndexer",
                        "size": 5_000_000_000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    },
                    {
                        "guid": "release-def",
                        "title": "Show.S01E01.1080p.WEB-DL",
                        "indexer": "TestIndexer",
                        "size": 2_000_000_000,
                        "quality": {"quality": {"id": 3, "name": "WEBDL-1080p"}},
                    },
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            releases = await client.get_episode_releases(1001)

        assert len(releases) == 2
        assert releases[0].guid == "release-abc"
        assert releases[0].is_4k() is True
        assert releases[1].guid == "release-def"
        assert releases[1].is_4k() is False


class TestGetLatestAiredEpisode:
    """Tests for get_latest_aired_episode method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_most_recent_aired_episode(self) -> None:
        """Should return the episode with the most recent air date that has aired."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)
        tomorrow = today + timedelta(days=1)

        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "title": "Oldest",
                        "airDate": last_week.isoformat(),
                        "monitored": True,
                    },
                    {
                        "id": 1002,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "title": "Yesterday",
                        "airDate": yesterday.isoformat(),
                        "monitored": True,
                    },
                    {
                        "id": 1003,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 3,
                        "title": "Future",
                        "airDate": tomorrow.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            latest = await client.get_latest_aired_episode(123)

        assert latest is not None
        assert latest.id == 1002
        assert latest.title == "Yesterday"

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_none_when_no_episodes_aired(self) -> None:
        """Should return None if no episodes have aired yet."""
        tomorrow = date.today() + timedelta(days=1)
        next_week = date.today() + timedelta(days=7)

        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "title": "Future1",
                        "airDate": tomorrow.isoformat(),
                        "monitored": True,
                    },
                    {
                        "id": 1002,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "title": "Future2",
                        "airDate": next_week.isoformat(),
                        "monitored": True,
                    },
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            latest = await client.get_latest_aired_episode(123)

        assert latest is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_none_when_no_episodes(self) -> None:
        """Should return None if series has no episodes."""
        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(return_value=Response(200, json=[]))

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            latest = await client.get_latest_aired_episode(123)

        assert latest is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_handles_episodes_without_air_date(self) -> None:
        """Should skip episodes without air dates."""
        yesterday = date.today() - timedelta(days=1)

        respx.get(
            "http://sonarr:8989/api/v3/episode", params={"seriesId": "123"}
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1001,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "title": "Has Date",
                        "airDate": yesterday.isoformat(),
                        "monitored": True,
                    },
                    {
                        "id": 1002,
                        "seriesId": 123,
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "title": "No Date",
                        "monitored": True,
                        # airDate not present
                    },
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            latest = await client.get_latest_aired_episode(123)

        assert latest is not None
        assert latest.id == 1001


class TestSonarrModels:
    """Tests for Sonarr-specific models."""

    def test_episode_model_with_aliases(self) -> None:
        """Should parse episode data with field aliases."""
        from findarr.models.sonarr import Episode

        episode = Episode.model_validate(
            {
                "id": 100,
                "seriesId": 50,
                "seasonNumber": 2,
                "episodeNumber": 5,
                "title": "Test Episode",
                "airDate": "2024-06-15",
                "airDateUtc": "2024-06-15T19:00:00Z",
                "hasFile": True,
                "monitored": False,
            }
        )

        assert episode.id == 100
        assert episode.series_id == 50
        assert episode.season_number == 2
        assert episode.episode_number == 5
        assert episode.air_date == date(2024, 6, 15)
        assert episode.has_file is True
        assert episode.monitored is False

    def test_season_model_with_aliases(self) -> None:
        """Should parse season data with field aliases."""
        from findarr.models.sonarr import Season

        season = Season(
            seasonNumber=3,
            monitored=True,
            **{
                "statistics.episodeCount": 12,
                "statistics.episodeFileCount": 10,
            },
        )

        assert season.season_number == 3
        assert season.monitored is True
        assert season.episode_count == 12
        assert season.episode_file_count == 10

    def test_series_model(self) -> None:
        """Should parse series data with seasons."""
        from findarr.models.sonarr import Season, Series

        series = Series(
            id=200,
            title="My Show",
            year=2023,
            seasons=[
                Season(seasonNumber=1, monitored=True),
                Season(seasonNumber=2, monitored=False),
            ],
            monitored=True,
        )

        assert series.id == 200
        assert series.title == "My Show"
        assert series.year == 2023
        assert len(series.seasons) == 2
