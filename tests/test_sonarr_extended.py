"""Extended tests for Sonarr client edge cases."""

import pytest
import respx
from httpx import Response

from filtarr.clients.sonarr import SonarrClient


class TestGetSeriesFromList:
    """Tests for finding a specific series from the library list."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_series_no_matches(self) -> None:
        """Should return empty list when no series match search term."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Breaking Bad",
                        "year": 2008,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                    {
                        "id": 2,
                        "title": "The Wire",
                        "year": 2002,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            results = await client.search_series("nonexistent show")

        assert results == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_not_found(self) -> None:
        """Should return None when series is not found by name."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Breaking Bad",
                        "year": 2008,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            result = await client.find_series_by_name("The Wire")

        assert result is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_exact_match(self) -> None:
        """Should return series with exact match."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Breaking Bad",
                        "year": 2008,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                    {
                        "id": 2,
                        "title": "Breaking Bad: Better Call Saul",
                        "year": 2015,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            result = await client.find_series_by_name("Breaking Bad")

        assert result is not None
        assert result.id == 1
        assert result.title == "Breaking Bad"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_returns_shortest_match(self) -> None:
        """Should return series with shortest title when no exact match."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Bad Things Happen in Philadelphia",
                        "year": 2020,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                    {
                        "id": 2,
                        "title": "Breaking Bad: Extended",
                        "year": 2008,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                    {
                        "id": 3,
                        "title": "Bad Day at Black Rock",
                        "year": 1955,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            result = await client.find_series_by_name("bad")

        assert result is not None
        # Should return the one with shortest title containing "bad"
        assert result.id == 3
        assert result.title == "Bad Day at Black Rock"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_series_by_name_case_insensitive(self) -> None:
        """Should match series name case-insensitively."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "BREAKING BAD",
                        "year": 2008,
                        "monitored": True,
                        "seasons": [],
                        "tags": [],
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            result = await client.find_series_by_name("breaking bad")

        assert result is not None
        assert result.id == 1


class TestGetAllSeries:
    """Tests for get_all_series method."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_all_series_empty(self) -> None:
        """Should return empty list when no series exist."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(return_value=Response(200, json=[]))

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.get_all_series()

        assert series == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_all_series_with_seasons(self) -> None:
        """Should parse series with seasons correctly."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
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
                        "tags": [1, 2],
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series_list = await client.get_all_series()

        assert len(series_list) == 1
        series = series_list[0]
        assert series.id == 1
        assert series.title == "Test Show"
        assert len(series.seasons) == 2
        assert series.seasons[0].episode_count == 10
        assert series.tags == [1, 2]

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_all_series_missing_statistics(self) -> None:
        """Should handle missing statistics in seasons."""
        respx.get("http://127.0.0.1:8989/api/v3/series").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "id": 1,
                        "title": "Test Show",
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
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series_list = await client.get_all_series()

        assert len(series_list) == 1
        assert series_list[0].seasons[0].episode_count == 0
        assert series_list[0].seasons[0].episode_file_count == 0


class TestSeriesTagOperations:
    """Tests for series tag management operations."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_tag_to_series_success(self) -> None:
        """Should add tag to series successfully."""
        # Mock getting the series
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Show",
                    "year": 2024,
                    "monitored": True,
                    "seasons": [],
                    "tags": [1, 2],
                },
            )
        )
        # Mock updating the series
        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Show",
                    "year": 2024,
                    "monitored": True,
                    "seasons": [],
                    "tags": [1, 2, 3],
                },
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.add_tag_to_series(123, 3)

        assert 3 in series.tags
        assert series.tags == [1, 2, 3]

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_tag_to_series_tag_already_exists(self) -> None:
        """Should not duplicate tag if already exists."""
        # Mock getting the series - tag 2 already exists
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Show",
                    "year": 2024,
                    "monitored": True,
                    "seasons": [],
                    "tags": [1, 2],
                },
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.add_tag_to_series(123, 2)

        assert series.tags == [1, 2]

    @respx.mock
    @pytest.mark.asyncio
    async def test_remove_tag_from_series_success(self) -> None:
        """Should remove tag from series successfully."""
        # Mock getting the series
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Show",
                    "year": 2024,
                    "monitored": True,
                    "seasons": [],
                    "tags": [1, 2, 3],
                },
            )
        )
        # Mock updating the series
        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Show",
                    "year": 2024,
                    "monitored": True,
                    "seasons": [],
                    "tags": [1, 3],
                },
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.remove_tag_from_series(123, 2)

        assert 2 not in series.tags
        assert series.tags == [1, 3]

    @respx.mock
    @pytest.mark.asyncio
    async def test_remove_tag_from_series_tag_not_present(self) -> None:
        """Should return series unchanged when tag not present."""
        # Mock getting the series - tag 99 doesn't exist
        respx.get("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(
                200,
                json={
                    "id": 123,
                    "title": "Test Show",
                    "year": 2024,
                    "monitored": True,
                    "seasons": [],
                    "tags": [1, 2],
                },
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            series = await client.remove_tag_from_series(123, 99)

        assert series.tags == [1, 2]


class TestSeriesReleases:
    """Tests for series release search."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_releases_empty(self) -> None:
        """Should return empty list when no releases found."""
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"seriesId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            releases = await client.get_series_releases(123)

        assert releases == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_releases_parses_quality(self) -> None:
        """Should parse quality information correctly."""
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "release-1",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "TestIndexer",
                        "size": 5_000_000_000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    },
                    {
                        "guid": "release-2",
                        "title": "Show.S01.1080p.WEB-DL",
                        "indexer": "TestIndexer",
                        "size": 2_000_000_000,
                        "quality": {"quality": {"id": 3, "name": "WEBDL-1080p"}},
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            releases = await client.get_series_releases(123)

        assert len(releases) == 2
        assert releases[0].quality.name == "WEBDL-2160p"
        assert releases[0].is_4k() is True
        assert releases[1].quality.name == "WEBDL-1080p"
        assert releases[1].is_4k() is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_true(self) -> None:
        """Should return True when 4K releases are available."""
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "release-1",
                        "title": "Show.S01.2160p.WEB-DL",
                        "indexer": "TestIndexer",
                        "size": 5_000_000_000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_false(self) -> None:
        """Should return False when no 4K releases are available."""
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"seriesId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "release-1",
                        "title": "Show.S01.1080p.WEB-DL",
                        "indexer": "TestIndexer",
                        "size": 2_000_000_000,
                        "quality": {"quality": {"id": 3, "name": "WEBDL-1080p"}},
                    },
                ],
            )
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_empty(self) -> None:
        """Should return False when no releases found."""
        respx.get("http://127.0.0.1:8989/api/v3/release", params={"seriesId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is False


class TestSeriesApiCaching:
    """Tests for series API response caching behavior."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_update_series_invalidates_cache(self) -> None:
        """Should invalidate cache after updating series."""
        series_data = {
            "id": 123,
            "title": "Test Show",
            "year": 2024,
            "monitored": True,
            "seasons": [],
            "tags": [1, 2],
        }
        respx.put("http://127.0.0.1:8989/api/v3/series/123").mock(
            return_value=Response(200, json=series_data)
        )

        async with SonarrClient("http://127.0.0.1:8989", "test-api-key") as client:
            # The update_series method calls invalidate_cache internally
            series = await client.update_series(series_data)

        assert series.id == 123
        assert series.tags == [1, 2]
