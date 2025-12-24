"""Tests for BaseArrClient retry and caching functionality."""

import pytest
import respx
from httpx import ConnectError, ConnectTimeout, ReadTimeout, Response

from filtarr.clients.radarr import RadarrClient


class TestCaching:
    """Tests for TTL caching functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self) -> None:
        """Should return cached data on second call without making HTTP request."""
        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "abc",
                        "title": "Movie.2160p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            # First call - should hit the API
            releases1 = await client.get_movie_releases(123)
            assert route.call_count == 1

            # Second call - should use cache
            releases2 = await client.get_movie_releases(123)
            assert route.call_count == 1  # Still 1, not 2

            # Both should return the same data
            assert releases1[0].guid == releases2[0].guid

    @respx.mock
    @pytest.mark.asyncio
    async def test_different_params_not_cached(self) -> None:
        """Should make separate requests for different parameters."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "abc",
                        "title": "Movie1.2160p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "xyz",
                        "title": "Movie2.1080p",
                        "indexer": "Test",
                        "size": 2000,
                        "quality": {"quality": {"id": 7, "name": "Bluray-1080p"}},
                    }
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            releases1 = await client.get_movie_releases(123)
            releases2 = await client.get_movie_releases(456)

            assert releases1[0].guid == "abc"
            assert releases2[0].guid == "xyz"

    @respx.mock
    @pytest.mark.asyncio
    async def test_invalidate_cache(self) -> None:
        """Should remove entry when invalidate_cache is called."""
        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "abc",
                        "title": "Movie.2160p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            # First call - caches result
            await client.get_movie_releases(123)
            assert route.call_count == 1

            # Invalidate cache
            removed = await client.invalidate_cache("/api/v3/release", {"movieId": 123})
            assert removed is True

            # Next call should hit API again
            await client.get_movie_releases(123)
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_clear_cache(self) -> None:
        """Should clear all cached entries."""
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )
        respx.get("http://radarr:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(200, json=[])
        )

        async with RadarrClient("http://radarr:7878", "test-api-key") as client:
            await client.get_movie_releases(123)
            await client.get_movie_releases(456)

            count = await client.clear_cache()
            assert count == 2


class TestRetry:
    """Tests for retry functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_connect_error(self) -> None:
        """Should retry on connection errors."""
        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"})
        # First call fails, second succeeds
        route.side_effect = [
            ConnectError("Connection refused"),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://radarr:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_timeout(self) -> None:
        """Should retry on timeout errors."""
        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            ConnectTimeout("Timeout"),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://radarr:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_read_timeout(self) -> None:
        """Should retry on read timeout errors."""
        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            ReadTimeout("Read timeout"),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://radarr:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_401(self) -> None:
        """Should NOT retry on 401 Unauthorized - fail fast."""
        from httpx import HTTPStatusError

        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )

        async with RadarrClient("http://radarr:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 401
            assert route.call_count == 1  # No retries

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_404(self) -> None:
        """Should NOT retry on 404 Not Found - fail fast."""
        from httpx import HTTPStatusError

        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        async with RadarrClient("http://radarr:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 404
            assert route.call_count == 1  # No retries

    @respx.mock
    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self) -> None:
        """Should raise original exception after exhausting all retry attempts."""
        route = respx.get("http://radarr:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = ConnectError("Connection refused")

        async with RadarrClient("http://radarr:7878", "test-api-key", max_retries=3) as client:
            # reraise=True means original exception is raised after retries exhausted
            with pytest.raises(ConnectError):
                await client.get_movie_releases(123)

            assert route.call_count == 3
