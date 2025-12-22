"""Tests for API clients."""

import pytest
import respx
from httpx import Response

from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient


class TestRadarrClient:
    """Tests for RadarrClient."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_movie_releases(self, sample_radarr_response: list[dict]) -> None:
        """Should parse releases from Radarr API response."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=sample_radarr_response)
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            releases = await client.get_movie_releases(123)

        assert len(releases) == 2
        assert releases[0].title == "Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP"
        assert releases[0].is_4k() is True
        assert releases[1].is_4k() is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_true(self, sample_radarr_response: list[dict]) -> None:
        """Should return True when 4K releases exist."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=sample_radarr_response)
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_has_4k_releases_false(self) -> None:
        """Should return False when no 4K releases exist."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "abc",
                        "title": "Movie.1080p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            has_4k = await client.has_4k_releases(123)

        assert has_4k is False

    @pytest.mark.asyncio
    async def test_client_not_in_context_raises(self) -> None:
        """Should raise when client used outside context manager."""
        client = RadarrClient("http://radarr:7878", "test-api-key")
        with pytest.raises(RuntimeError, match="must be used within async context"):
            _ = client.client


class TestSonarrClient:
    """Tests for SonarrClient."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_series_releases(self) -> None:
        """Should parse releases from Sonarr API response."""
        respx.get("http://sonarr:8989/api/v3/release", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "xyz789",
                        "title": "Show.S01E01.2160p.WEB-DL",
                        "indexer": "TestIndexer",
                        "size": 5_000_000_000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        async with SonarrClient("http://sonarr:8989", "test-api-key") as client:
            releases = await client.get_series_releases(456)

        assert len(releases) == 1
        assert releases[0].is_4k() is True
