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

    def test_parse_release_4k_detection_relies_on_quality_not_title(self) -> None:
        """4K detection relies on Quality, not title parsing.

        When quality is 'Unknown', we trust Radarr/Sonarr's quality parsing
        rather than doing our own title matching which causes false positives
        (e.g., release groups like '4K4U' being detected as 4K content).
        """
        item = {
            "guid": "4k-title",
            "title": "Movie.2024.2160p.WEB-DL",
            "quality": {"quality": {"id": 1, "name": "Unknown"}},
        }

        release = BaseArrClient._parse_release(item)

        # Quality is "Unknown", so this is NOT considered 4K
        assert release.is_4k() is False


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


class TestHTTPStatusRetry:
    """Tests for retry behavior on HTTP status errors (429, 5xx)."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self) -> None:
        """Should retry on 429 Too Many Requests response."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        # First call returns 429, second succeeds
        route.side_effect = [
            Response(429, json={"error": "Too Many Requests"}),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2  # First failed, second succeeded

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_500_internal_server_error(self) -> None:
        """Should retry on 500 Internal Server Error."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            Response(500, json={"error": "Internal Server Error"}),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_502_bad_gateway(self) -> None:
        """Should retry on 502 Bad Gateway."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            Response(502, json={"error": "Bad Gateway"}),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_503_service_unavailable(self) -> None:
        """Should retry on 503 Service Unavailable."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            Response(503, json={"error": "Service Unavailable"}),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_504_gateway_timeout(self) -> None:
        """Should retry on 504 Gateway Timeout."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            Response(504, json={"error": "Gateway Timeout"}),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_max_retries_exhausted_on_429(self) -> None:
        """Should raise after exhausting all retries on persistent 429."""
        from httpx import HTTPStatusError

        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        # All calls return 429
        route.side_effect = [
            Response(429, json={"error": "Too Many Requests"}),
            Response(429, json={"error": "Too Many Requests"}),
            Response(429, json={"error": "Too Many Requests"}),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 429
            assert route.call_count == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_max_retries_exhausted_on_5xx(self) -> None:
        """Should raise after exhausting all retries on persistent 5xx."""
        from httpx import HTTPStatusError

        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        route.side_effect = [
            Response(503, json={"error": "Service Unavailable"}),
            Response(503, json={"error": "Service Unavailable"}),
            Response(503, json={"error": "Service Unavailable"}),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 503
            assert route.call_count == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_with_retry_after_header_respects_delay(self) -> None:
        """Should respect Retry-After header when present on 429 response."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        # First call returns 429 with Retry-After header, second succeeds
        route.side_effect = [
            Response(
                429,
                json={"error": "Too Many Requests"},
                headers={"Retry-After": "1"},  # Wait 1 second
            ),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            start_time = time.monotonic()
            releases = await client.get_movie_releases(123)
            elapsed = time.monotonic() - start_time

            assert releases == []
            assert route.call_count == 2
            # Should have waited at least 1 second due to Retry-After header
            assert elapsed >= 1.0

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_400_bad_request(self) -> None:
        """Should NOT retry on 400 Bad Request - fail fast."""
        from httpx import HTTPStatusError

        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(400, json={"error": "Bad Request"})
        )

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 400
            assert route.call_count == 1  # No retries

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_retry_on_403_forbidden(self) -> None:
        """Should NOT retry on 403 Forbidden - fail fast."""
        from httpx import HTTPStatusError

        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(403, json={"error": "Forbidden"})
        )

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=3) as client:
            with pytest.raises(HTTPStatusError) as exc_info:
                await client.get_movie_releases(123)

            assert exc_info.value.response.status_code == 403
            assert route.call_count == 1  # No retries

    @respx.mock
    @pytest.mark.asyncio
    async def test_mixed_retry_scenarios(self) -> None:
        """Should handle mixed error scenarios correctly."""
        route = respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"})
        # First 429, then 503, then success
        route.side_effect = [
            Response(429, json={"error": "Too Many Requests"}),
            Response(503, json={"error": "Service Unavailable"}),
            Response(200, json=[]),
        ]

        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=4) as client:
            releases = await client.get_movie_releases(123)
            assert releases == []
            assert route.call_count == 3


class TestReleaseProviderProtocol:
    """Tests for ReleaseProvider Protocol compliance."""

    def test_radarr_client_satisfies_release_provider_protocol(self) -> None:
        """RadarrClient should satisfy ReleaseProvider protocol at runtime."""
        from filtarr.clients.base import ReleaseProvider

        client = RadarrClient("http://localhost:7878", "test-api-key")
        assert isinstance(client, ReleaseProvider)

    def test_sonarr_client_satisfies_release_provider_protocol(self) -> None:
        """SonarrClient should satisfy ReleaseProvider protocol at runtime."""
        from filtarr.clients.base import ReleaseProvider
        from filtarr.clients.sonarr import SonarrClient

        client = SonarrClient("http://localhost:8989", "test-api-key")
        assert isinstance(client, ReleaseProvider)

    def test_release_provider_is_runtime_checkable(self) -> None:
        """ReleaseProvider should be runtime_checkable for isinstance checks."""
        from filtarr.clients.base import ReleaseProvider

        # Verify the protocol has the runtime_checkable decorator
        assert hasattr(ReleaseProvider, "__protocol_attrs__") or hasattr(
            ReleaseProvider, "_is_runtime_protocol"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_radarr_get_releases_for_item_works(self) -> None:
        """RadarrClient.get_releases_for_item should return releases."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
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
            releases = await client.get_releases_for_item(123)
            assert len(releases) == 1
            assert releases[0].guid == "abc"

    @respx.mock
    @pytest.mark.asyncio
    async def test_sonarr_get_releases_for_item_works(self) -> None:
        """SonarrClient.get_releases_for_item should return releases."""
        from filtarr.clients.sonarr import SonarrClient

        respx.get("http://localhost:8989/api/v3/release", params={"seriesId": "456"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "xyz",
                        "title": "Show.S01E01.2160p",
                        "indexer": "Test",
                        "size": 2000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        async with SonarrClient("http://localhost:8989", "test-api-key") as client:
            releases = await client.get_releases_for_item(456)
            assert len(releases) == 1
            assert releases[0].guid == "xyz"

    @pytest.mark.asyncio
    async def test_mock_release_provider_usable(self) -> None:
        """A mock ReleaseProvider should be usable in place of real clients."""
        from unittest.mock import AsyncMock

        from filtarr.clients.base import ReleaseProvider
        from filtarr.models.common import Quality, Release

        # Create a mock that satisfies the protocol
        mock_provider = AsyncMock(spec=ReleaseProvider)
        mock_provider.get_releases_for_item.return_value = [
            Release(
                guid="mock-guid",
                title="Mock.Release.2160p",
                indexer="MockIndexer",
                size=1000,
                quality=Quality(id=19, name="WEBDL-2160p"),
            )
        ]

        # Verify the mock works
        releases = await mock_provider.get_releases_for_item(123)
        assert len(releases) == 1
        assert releases[0].guid == "mock-guid"
        mock_provider.get_releases_for_item.assert_called_once_with(123)

    def test_base_arr_client_does_not_satisfy_release_provider(self) -> None:
        """BaseArrClient itself should NOT satisfy ReleaseProvider (abstract)."""
        from filtarr.clients.base import BaseArrClient, ReleaseProvider

        client = BaseArrClient("http://localhost:7878", "test-api-key")
        # BaseArrClient doesn't implement get_releases_for_item, so should not match
        assert not isinstance(client, ReleaseProvider)


class TestCacheStampedeProtection:
    """Tests for cache thundering herd / stampede protection."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_concurrent_requests_only_trigger_one_api_call(self) -> None:
        """Concurrent requests for same cache key should only trigger one API call.

        This tests the cache stampede/thundering herd protection. When multiple
        concurrent requests arrive for the same uncached key, only the first
        should hit the API while others wait.
        """
        import asyncio

        import httpx

        # Track how many times the API is called
        call_count = 0

        async def mock_response(_request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            # Add a small delay to simulate API latency
            await asyncio.sleep(0.1)
            return Response(
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

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            side_effect=mock_response
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            # Fire 5 concurrent requests for the same movie
            tasks = [client.get_movie_releases(123) for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # All results should be identical
            assert all(len(r) == 1 for r in results)
            assert all(r[0].guid == "abc" for r in results)

            # Only ONE API call should have been made (stampede protection)
            assert call_count == 1, f"Expected 1 API call, got {call_count}"

    @respx.mock
    @pytest.mark.asyncio
    async def test_second_request_waits_for_first_to_complete(self) -> None:
        """Second concurrent request should wait for first request to complete.

        The second request should not start its own API call but instead wait
        for the first request's result.
        """
        import asyncio

        import httpx

        request_start_times: list[float] = []
        response_times: list[float] = []

        async def mock_response(_request: httpx.Request) -> Response:
            request_start_times.append(time.monotonic())
            await asyncio.sleep(0.2)  # Simulate slow API
            response_times.append(time.monotonic())
            return Response(200, json=[])

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            side_effect=mock_response
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            start_time = time.monotonic()
            tasks = [client.get_movie_releases(123) for _ in range(3)]
            await asyncio.gather(*tasks)
            total_elapsed = time.monotonic() - start_time

            # Only one request should have been made
            assert len(request_start_times) == 1, "Only one API request should be made"

            # Total time should be around 0.2s (one request), not 0.6s (three sequential)
            assert total_elapsed < 0.5, (
                f"Total time {total_elapsed}s suggests requests didn't share results"
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_concurrent_requests_receive_same_cached_result(self) -> None:
        """All concurrent requests should receive the exact same cached result object."""
        import asyncio

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "guid": "unique-guid-123",
                        "title": "Cached.Movie.2160p",
                        "indexer": "Test",
                        "size": 5000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tasks = [client.get_movie_releases(123) for _ in range(3)]
            results = await asyncio.gather(*tasks)

            # All results should have the same content
            for result in results:
                assert len(result) == 1
                assert result[0].guid == "unique-guid-123"
                assert result[0].title == "Cached.Movie.2160p"

    @respx.mock
    @pytest.mark.asyncio
    async def test_error_in_first_request_propagates_to_all_waiters(self) -> None:
        """If the first request fails, all waiters should receive the same error.

        This ensures that when stampede protection coalesces multiple requests,
        an error in the "leader" request propagates to all waiting requests.
        """
        import asyncio

        import httpx
        from httpx import HTTPStatusError

        call_count = 0

        async def mock_error_response(_request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return Response(401, json={"error": "Unauthorized"})

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            side_effect=mock_error_response
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            tasks = [client.get_movie_releases(123) for _ in range(3)]

            # All tasks should fail with the same error
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All results should be HTTPStatusError with 401
            for result in results:
                assert isinstance(result, HTTPStatusError)
                assert result.response.status_code == 401

            # Only ONE API call should have been made
            assert call_count == 1, f"Expected 1 API call, got {call_count}"

    @respx.mock
    @pytest.mark.asyncio
    async def test_different_cache_keys_make_separate_requests(self) -> None:
        """Different cache keys should NOT share requests (only same key coalescses)."""
        import asyncio

        import httpx

        call_count = 0

        async def mock_response(request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            movie_id = request.url.params.get("movieId")
            return Response(
                200,
                json=[
                    {
                        "guid": f"guid-{movie_id}",
                        "title": f"Movie{movie_id}.2160p",
                        "indexer": "Test",
                        "size": 1000,
                        "quality": {"quality": {"id": 19, "name": "WEBDL-2160p"}},
                    }
                ],
            )

        respx.get("http://localhost:7878/api/v3/release").mock(side_effect=mock_response)

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            # Request 3 different movies concurrently
            tasks = [
                client.get_movie_releases(123),
                client.get_movie_releases(456),
                client.get_movie_releases(789),
            ]
            results = await asyncio.gather(*tasks)

            # Each should have their own result
            assert results[0][0].guid == "guid-123"
            assert results[1][0].guid == "guid-456"
            assert results[2][0].guid == "guid-789"

            # Three separate API calls for three different movies
            assert call_count == 3, f"Expected 3 API calls, got {call_count}"

    @respx.mock
    @pytest.mark.asyncio
    async def test_retryable_error_in_first_request_propagates_to_waiters(self) -> None:
        """If the first request fails with a retryable error, waiters get the error too.

        After retries are exhausted, the error should propagate to all waiting requests.
        """
        import asyncio

        import httpx
        from httpx import HTTPStatusError

        call_count = 0

        async def mock_503_response(_request: httpx.Request) -> Response:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return Response(503, json={"error": "Service Unavailable"})

        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            side_effect=mock_503_response
        )

        # Use max_retries=1 to speed up the test
        async with RadarrClient("http://localhost:7878", "test-api-key", max_retries=1) as client:
            tasks = [client.get_movie_releases(123) for _ in range(3)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All results should be HTTPStatusError with 503
            for result in results:
                assert isinstance(result, HTTPStatusError)
                assert result.response.status_code == 503

            # The "leader" request should have made 1 attempt (max_retries=1)
            # With stampede protection, waiters don't make their own calls
            assert call_count == 1, f"Expected 1 API call, got {call_count}"


class TestRetryableHTTPError:
    """Tests for RetryableHTTPError exception class."""

    def test_status_code_property_returns_response_status(self) -> None:
        """RetryableHTTPError.status_code should return the response's status code."""
        from filtarr.clients.base import RetryableHTTPError

        # Create a mock response with a specific status code
        response = Response(429, json={"error": "Too Many Requests"})
        error = RetryableHTTPError("Rate limited", response=response, retry_after=5.0)

        assert error.status_code == 429

    def test_status_code_property_for_5xx_errors(self) -> None:
        """RetryableHTTPError.status_code should work for 5xx error codes."""
        from filtarr.clients.base import RetryableHTTPError

        response = Response(503, json={"error": "Service Unavailable"})
        error = RetryableHTTPError("Server error", response=response)

        assert error.status_code == 503

    def test_retry_after_stored_correctly(self) -> None:
        """RetryableHTTPError should store retry_after value."""
        from filtarr.clients.base import RetryableHTTPError

        response = Response(429, json={"error": "Rate limited"})
        error = RetryableHTTPError("Rate limited", response=response, retry_after=10.5)

        assert error.retry_after == 10.5

    def test_retry_after_defaults_to_none(self) -> None:
        """RetryableHTTPError.retry_after should default to None."""
        from filtarr.clients.base import RetryableHTTPError

        response = Response(500, json={"error": "Server error"})
        error = RetryableHTTPError("Server error", response=response)

        assert error.retry_after is None


class TestRetryPredicate:
    """Tests for RetryPredicate class."""

    def test_returns_false_when_outcome_is_none(self) -> None:
        """RetryPredicate should return False when retry_state.outcome is None."""
        from unittest.mock import MagicMock

        from filtarr.clients.base import RetryPredicate

        predicate = RetryPredicate()

        # Create a mock retry state with outcome = None
        retry_state = MagicMock()
        retry_state.outcome = None

        result = predicate(retry_state)

        assert result is False

    def test_returns_false_when_no_exception(self) -> None:
        """RetryPredicate should return False when outcome has no exception."""
        from unittest.mock import MagicMock

        from filtarr.clients.base import RetryPredicate

        predicate = RetryPredicate()

        # Create a mock retry state where outcome.exception() returns None
        retry_state = MagicMock()
        retry_state.outcome.exception.return_value = None

        result = predicate(retry_state)

        assert result is False

    def test_returns_true_for_connect_error(self) -> None:
        """RetryPredicate should return True for ConnectError."""
        from unittest.mock import MagicMock

        from filtarr.clients.base import RetryPredicate

        predicate = RetryPredicate()

        retry_state = MagicMock()
        retry_state.outcome.exception.return_value = ConnectError("Connection refused")

        result = predicate(retry_state)

        assert result is True

    def test_returns_true_for_connect_timeout(self) -> None:
        """RetryPredicate should return True for ConnectTimeout."""
        from unittest.mock import MagicMock

        from filtarr.clients.base import RetryPredicate

        predicate = RetryPredicate()

        retry_state = MagicMock()
        retry_state.outcome.exception.return_value = ConnectTimeout("Connection timeout")

        result = predicate(retry_state)

        assert result is True

    def test_returns_true_for_read_timeout(self) -> None:
        """RetryPredicate should return True for ReadTimeout."""
        from unittest.mock import MagicMock

        from filtarr.clients.base import RetryPredicate

        predicate = RetryPredicate()

        retry_state = MagicMock()
        retry_state.outcome.exception.return_value = ReadTimeout("Read timeout")

        result = predicate(retry_state)

        assert result is True

    def test_returns_true_for_retryable_http_error(self) -> None:
        """RetryPredicate should return True for RetryableHTTPError."""
        from unittest.mock import MagicMock

        from filtarr.clients.base import RetryableHTTPError, RetryPredicate

        predicate = RetryPredicate()

        response = Response(503, json={"error": "Service Unavailable"})
        retry_state = MagicMock()
        retry_state.outcome.exception.return_value = RetryableHTTPError(
            "Server error", response=response
        )

        result = predicate(retry_state)

        assert result is True

    def test_returns_false_for_other_exceptions(self) -> None:
        """RetryPredicate should return False for non-retryable exceptions."""
        from unittest.mock import MagicMock

        from filtarr.clients.base import RetryPredicate

        predicate = RetryPredicate()

        retry_state = MagicMock()
        retry_state.outcome.exception.return_value = ValueError("Some other error")

        result = predicate(retry_state)

        assert result is False


class TestConnectionPoolConfiguration:
    """Tests for explicit connection pool configuration (Task 4.5)."""

    def test_max_connections_parameter_default_value(self) -> None:
        """BaseArrClient should have default max_connections value of 20."""
        client = BaseArrClient("http://localhost:7878", "test-api-key")
        assert client.max_connections == 20

    def test_max_keepalive_connections_parameter_default_value(self) -> None:
        """BaseArrClient should have default max_keepalive_connections value of 10."""
        client = BaseArrClient("http://localhost:7878", "test-api-key")
        assert client.max_keepalive_connections == 10

    def test_max_connections_parameter_is_configurable(self) -> None:
        """max_connections should be configurable via constructor parameter."""
        client = BaseArrClient("http://localhost:7878", "test-api-key", max_connections=50)
        assert client.max_connections == 50

    def test_max_keepalive_connections_parameter_is_configurable(self) -> None:
        """max_keepalive_connections should be configurable via constructor parameter."""
        client = BaseArrClient(
            "http://localhost:7878", "test-api-key", max_keepalive_connections=25
        )
        assert client.max_keepalive_connections == 25

    @respx.mock
    @pytest.mark.asyncio
    async def test_limits_object_passed_to_async_client(self) -> None:
        """httpx.Limits object should be correctly passed to AsyncClient constructor."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        async with RadarrClient(
            "http://localhost:7878",
            "test-api-key",
            max_connections=30,
            max_keepalive_connections=15,
        ) as client:
            # Access the internal httpx client
            internal_client = client._client
            assert internal_client is not None

            # Verify the limits are set correctly on the connection pool
            # httpx stores limits in the transport's pool object
            pool = internal_client._transport._pool
            assert pool._max_connections == 30
            assert pool._max_keepalive_connections == 15

    @respx.mock
    @pytest.mark.asyncio
    async def test_default_limits_applied_when_not_specified(self) -> None:
        """Default limits (20/10) should be applied when not specified."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        async with RadarrClient("http://localhost:7878", "test-api-key") as client:
            # Access the internal httpx client
            internal_client = client._client
            assert internal_client is not None

            # Verify default limits on the connection pool
            pool = internal_client._transport._pool
            assert pool._max_connections == 20
            assert pool._max_keepalive_connections == 10

    @respx.mock
    @pytest.mark.asyncio
    async def test_radarr_client_inherits_connection_pool_config(self) -> None:
        """RadarrClient should support connection pool configuration from BaseArrClient."""
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        client = RadarrClient(
            "http://localhost:7878",
            "test-api-key",
            max_connections=40,
            max_keepalive_connections=20,
        )
        assert client.max_connections == 40
        assert client.max_keepalive_connections == 20

    @respx.mock
    @pytest.mark.asyncio
    async def test_sonarr_client_inherits_connection_pool_config(self) -> None:
        """SonarrClient should support connection pool configuration from BaseArrClient."""
        from filtarr.clients.sonarr import SonarrClient

        respx.get("http://localhost:8989/api/v3/release", params={"seriesId": "123"}).mock(
            return_value=Response(200, json=[])
        )

        client = SonarrClient(
            "http://localhost:8989",
            "test-api-key",
            max_connections=40,
            max_keepalive_connections=20,
        )
        assert client.max_connections == 40
        assert client.max_keepalive_connections == 20
