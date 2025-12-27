"""Tests for BaseArrClient retry and caching functionality."""

import logging
import time
from unittest.mock import patch

import pytest
import respx
from httpx import ConnectError, ConnectTimeout, ReadTimeout, Response

from filtarr.clients.base import BaseArrClient
from filtarr.clients.radarr import RadarrClient


class TestCaching:
    """Tests for TTL caching functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self) -> None:
        """Should return cached data on second call without making HTTP request."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
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

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
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
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
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
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
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

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            releases1 = await client.get_movie_releases(123)
            releases2 = await client.get_movie_releases(456)

            assert releases1[0].guid == "abc"
            assert releases2[0].guid == "xyz"

    @respx.mock
    @pytest.mark.asyncio
    async def test_invalidate_cache(self) -> None:
        """Should remove entry when invalidate_cache is called."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
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

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
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
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "456"}).mock(
            return_value=Response(200, json=[])
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
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
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        # First call fails, second succeeds
        route.side_effect = [
            ConnectError("Connection refused"),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_timeout(self) -> None:
        """Should retry on timeout errors."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            ConnectTimeout("Timeout"),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_read_timeout(self) -> None:
        """Should retry on read timeout errors."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            ReadTimeout("Read timeout"),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_401(self) -> None:
        """Should NOT retry on 401 Unauthorized - fail fast."""
        from httpx import HTTPStatusError

        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 401
            assert route.call_count == 1  # No retries

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_404(self) -> None:
        """Should NOT retry on 404 Not Found - fail fast."""
        from httpx import HTTPStatusError

        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 404
            assert route.call_count == 1  # No retries

    @respx.mock
    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self) -> None:
        """Should raise original exception after exhausting all retry attempts."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = ConnectError("Connection refused")

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            # reraise=True means original exception is raised after retries exhausted
            with pytest.raises(ConnectError):
                await client.get_movie_releases(123)

            assert route.call_count == 3


class TestParseRelease:
    """Tests for _parse_release() static method."""

    def test_parse_release_full_data(self) -> None:
        """Should parse release with all fields populated."""
        item = {
            "guid": "abc123",
            "title": "Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP",
            "indexer": "TestIndexer",
            "size": 15_000_000_000,
            "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
        }

        release = BaseArrClient._parse_release(item)

        assert release.guid == "abc123"
        assert release.title == "Movie.Name.2024.2160p.UHD.BluRay.x265-GROUP"
        assert release.indexer == "TestIndexer"
        assert release.size == 15_000_000_000
        assert release.quality.id == 19
        assert release.quality.name == "WEBDL-2160p"
        assert release.is_4k() is True

    def test_parse_release_minimal_data(self) -> None:
        """Should parse release with only required fields, using defaults for optional."""
        item = {
            "guid": "xyz789",
            "title": "Movie.1080p",
        }

        release = BaseArrClient._parse_release(item)

        assert release.guid == "xyz789"
        assert release.title == "Movie.1080p"
        assert release.indexer == "Unknown"
        assert release.size == 0
        assert release.quality.id == 0
        assert release.quality.name == "Unknown"
        assert release.is_4k() is False

    def test_parse_release_missing_quality_nested(self) -> None:
        """Should handle missing nested quality structure."""
        item = {
            "guid": "test",
            "title": "Test Release",
            "indexer": "Indexer1",
            "size": 1000,
            "quality": {},  # Missing nested "quality" key
        }

        release = BaseArrClient._parse_release(item)

        assert release.quality.id == 0
        assert release.quality.name == "Unknown"

    def test_parse_release_empty_quality(self) -> None:
        """Should handle empty quality object at top level."""
        item = {
            "guid": "test2",
            "title": "Test Release 2",
            "indexer": "Indexer2",
            "size": 2000,
            # No "quality" key at all
        }

        release = BaseArrClient._parse_release(item)

        assert release.quality.id == 0
        assert release.quality.name == "Unknown"

    def test_parse_release_partial_quality(self) -> None:
        """Should handle partial quality data with some fields missing."""
        item = {
            "guid": "partial",
            "title": "Partial Quality Release",
            "quality": {"quality": {"id": 7}},  # Missing "name"
        }

        release = BaseArrClient._parse_release(item)

        assert release.quality.id == 7
        assert release.quality.name == "Unknown"

    def test_parse_release_4k_detection_via_quality_name(self) -> None:
        """Should detect 4K from quality name."""
        item = {
            "guid": "4k-quality",
            "title": "Movie.720p",  # Title says 720p
            "quality": {"quality": {"id": 19, "name": "Bluray-2160p"}},  # Quality is 4K
        }

        release = BaseArrClient._parse_release(item)

        assert release.is_4k() is True

    def test_parse_release_4k_detection_via_title(self) -> None:
        """Should detect 4K from title when quality name does not indicate 4K."""
        item = {
            "guid": "4k-title",
            "title": "Movie.2024.2160p.WEB-DL",
            "quality": {"quality": {"id": 1, "name": "Unknown"}},
        }

        release = BaseArrClient._parse_release(item)

        assert release.is_4k() is True


class TestTimingLogging:
    """Tests for request timing logging functionality."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_logs_warning_on_failed_request(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log warning with timing when request fails."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = ConnectError("Connection refused")

        with caplog.at_level(logging.WARNING, logger="filtarr.clients.base"):
            async with RadarrClient(
                "http://localhost:7878", "test-api-key", max_retries=1
            ) as client:
                with pytest.raises(ConnectError):
                    await client.get_movie_releases(123)

        # Check that warning was logged with timing info
        assert any("failed after" in record.message for record in caplog.records)
        assert any("/api/v3/release" in record.message for record in caplog.records)

    @respx.mock
    @pytest.mark.asyncio
    async def test_successful_request_does_not_log_at_default_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Should not log warning for fast successful requests."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        with caplog.at_level(logging.WARNING, logger="filtarr.clients.base"):
            async with RadarrClient("http://localhost:7878", "test-api-key") as client:
                await client.get_movie_releases(123)

        # Fast requests should not trigger warning logs
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not any("Slow request" in r.message for r in warning_records)

    @respx.mock
    @pytest.mark.asyncio
    async def test_slow_request_logs_timing_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should log warning for requests taking longer than 5 seconds."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        # Mock time.monotonic to simulate 6 seconds elapsed
        call_count = 0

        def mock_monotonic() -> float:
            nonlocal call_count
            call_count += 1
            # First call returns 0, second call returns 6.0 (simulating 6 seconds)
            if call_count == 1:
                return 0.0
            return 6.0

        with (
            caplog.at_level(logging.WARNING, logger="filtarr.clients.base"),
            patch.object(time, "monotonic", mock_monotonic),
        ):
            async with RadarrClient("http://localhost:7878", "test-api-key") as client:
                await client.get_movie_releases(123)

        # Should have logged slow request warning
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("Slow request" in r.message for r in warning_records)
        assert any("6.00s" in r.message for r in warning_records)
        assert any("/api/v3/release" in r.message for r in warning_records)
