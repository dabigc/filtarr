"""Tests for ReleaseChecker connection pooling functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from filtarr.checker import ReleaseChecker
from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient


class TestReleaseCheckerContextManager:
    """Tests for ReleaseChecker async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_clients_on_enter(self) -> None:
        """Test that clients are created when entering context manager."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
            sonarr_url="http://localhost:8989",
            sonarr_api_key="test-key",
        )

        # Initially, clients should be None
        assert checker._radarr_client is None
        assert checker._sonarr_client is None
        assert checker._in_context is False

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(SonarrClient, "__aenter__", new_callable=AsyncMock) as sonarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock),
            patch.object(SonarrClient, "__aexit__", new_callable=AsyncMock),
        ):
            radarr_enter.return_value = None
            sonarr_enter.return_value = None

            async with checker:
                # After entering, clients should be created and _in_context should be True
                assert checker._radarr_client is not None
                assert checker._sonarr_client is not None
                assert checker._in_context is True

            # After exiting, clients should be cleaned up
            assert checker._radarr_client is None
            assert checker._sonarr_client is None
            assert checker._in_context is False

    @pytest.mark.asyncio
    async def test_context_manager_only_creates_configured_clients(self) -> None:
        """Test that only configured clients are created."""
        # Only Radarr configured
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock),
        ):
            radarr_enter.return_value = None

            async with checker:
                assert checker._radarr_client is not None
                assert checker._sonarr_client is None
                assert checker._in_context is True

    @pytest.mark.asyncio
    async def test_context_manager_clears_tag_cache_on_exit(self) -> None:
        """Test that tag cache is cleared when exiting context manager."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock),
        ):
            radarr_enter.return_value = None

            async with checker:
                # Simulate that tag cache was populated (on the tagger)
                checker._tagger._tag_cache = {"radarr": []}
                assert checker._tagger._tag_cache is not None

            # Tag cache should be cleared after exiting
            assert checker._tagger._tag_cache is None

    @pytest.mark.asyncio
    async def test_context_manager_returns_self(self) -> None:
        """Test that __aenter__ returns the checker instance."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock),
        ):
            radarr_enter.return_value = None

            async with checker as ctx:
                assert ctx is checker


class TestClientPoolingBehavior:
    """Tests for client reuse behavior."""

    @pytest.mark.asyncio
    async def test_get_radarr_client_uses_pooled_client_in_context(self) -> None:
        """Test that _get_radarr_client returns pooled client when in context."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock),
        ):
            radarr_enter.return_value = None

            async with checker:
                pooled_client = checker._radarr_client

                # Use _get_radarr_client and verify it yields the same client
                async with checker._get_radarr_client() as client:
                    assert client is pooled_client

    @pytest.mark.asyncio
    async def test_get_sonarr_client_uses_pooled_client_in_context(self) -> None:
        """Test that _get_sonarr_client returns pooled client when in context."""
        checker = ReleaseChecker(
            sonarr_url="http://localhost:8989",
            sonarr_api_key="test-key",
        )

        with (
            patch.object(SonarrClient, "__aenter__", new_callable=AsyncMock) as sonarr_enter,
            patch.object(SonarrClient, "__aexit__", new_callable=AsyncMock),
        ):
            sonarr_enter.return_value = None

            async with checker:
                pooled_client = checker._sonarr_client

                # Use _get_sonarr_client and verify it yields the same client
                async with checker._get_sonarr_client() as client:
                    assert client is pooled_client

    @pytest.mark.asyncio
    async def test_get_radarr_client_creates_temporary_client_outside_context(
        self,
    ) -> None:
        """Test that _get_radarr_client creates a new client outside context."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        assert checker._in_context is False
        assert checker._radarr_client is None

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock) as radarr_exit,
        ):
            radarr_enter.return_value = None

            # Use _get_radarr_client outside context manager
            async with checker._get_radarr_client() as client:
                # Should have created a temporary client
                assert client is not None
                radarr_enter.assert_called_once()

            # Client should have been cleaned up
            radarr_exit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_sonarr_client_creates_temporary_client_outside_context(
        self,
    ) -> None:
        """Test that _get_sonarr_client creates a new client outside context."""
        checker = ReleaseChecker(
            sonarr_url="http://localhost:8989",
            sonarr_api_key="test-key",
        )

        assert checker._in_context is False
        assert checker._sonarr_client is None

        with (
            patch.object(SonarrClient, "__aenter__", new_callable=AsyncMock) as sonarr_enter,
            patch.object(SonarrClient, "__aexit__", new_callable=AsyncMock) as sonarr_exit,
        ):
            sonarr_enter.return_value = None

            # Use _get_sonarr_client outside context manager
            async with checker._get_sonarr_client() as client:
                # Should have created a temporary client
                assert client is not None
                sonarr_enter.assert_called_once()

            # Client should have been cleaned up
            sonarr_exit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_radarr_client_raises_if_not_configured(self) -> None:
        """Test that _get_radarr_client raises ValueError if not configured."""
        checker = ReleaseChecker()  # No config

        with pytest.raises(ValueError, match="Radarr is not configured"):
            async with checker._get_radarr_client():
                pass

    @pytest.mark.asyncio
    async def test_get_sonarr_client_raises_if_not_configured(self) -> None:
        """Test that _get_sonarr_client raises ValueError if not configured."""
        checker = ReleaseChecker()  # No config

        with pytest.raises(ValueError, match="Sonarr is not configured"):
            async with checker._get_sonarr_client():
                pass


class TestConnectionPoolingWithOperations:
    """Tests for connection pooling during actual operations."""

    @pytest.mark.asyncio
    async def test_multiple_check_movie_calls_reuse_client_in_context(self) -> None:
        """Test that multiple check_movie calls reuse the same client in context."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        mock_movie = AsyncMock()
        mock_movie.title = "Test Movie"
        mock_movie.id = 1
        mock_movie.tags = []

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock),
            patch.object(RadarrClient, "get_movie", new_callable=AsyncMock) as get_movie,
            patch.object(
                RadarrClient, "get_movie_releases", new_callable=AsyncMock
            ) as get_releases,
        ):
            radarr_enter.return_value = None
            get_movie.return_value = mock_movie
            get_releases.return_value = []

            async with checker:
                # Store the pooled client reference
                pooled_client = checker._radarr_client

                # Make multiple calls
                await checker.check_movie(1, apply_tags=False)
                await checker.check_movie(2, apply_tags=False)
                await checker.check_movie(3, apply_tags=False)

                # Client should still be the same (pooled)
                assert checker._radarr_client is pooled_client

            # __aenter__ should only have been called once for the pooled client
            radarr_enter.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_check_series_calls_reuse_client_in_context(self) -> None:
        """Test that multiple check_series calls reuse the same client in context."""
        checker = ReleaseChecker(
            sonarr_url="http://localhost:8989",
            sonarr_api_key="test-key",
        )

        mock_series = AsyncMock()
        mock_series.title = "Test Series"
        mock_series.id = 1
        mock_series.tags = []

        with (
            patch.object(SonarrClient, "__aenter__", new_callable=AsyncMock) as sonarr_enter,
            patch.object(SonarrClient, "__aexit__", new_callable=AsyncMock),
            patch.object(SonarrClient, "get_series", new_callable=AsyncMock) as get_series,
            patch.object(SonarrClient, "get_episodes", new_callable=AsyncMock) as get_episodes,
        ):
            sonarr_enter.return_value = None
            get_series.return_value = mock_series
            get_episodes.return_value = []  # No episodes = no releases to check

            async with checker:
                # Store the pooled client reference
                pooled_client = checker._sonarr_client

                # Make multiple calls
                await checker.check_series(1, apply_tags=False)
                await checker.check_series(2, apply_tags=False)
                await checker.check_series(3, apply_tags=False)

                # Client should still be the same (pooled)
                assert checker._sonarr_client is pooled_client

            # __aenter__ should only have been called once for the pooled client
            sonarr_enter.assert_called_once()

    @respx.mock
    @pytest.mark.asyncio
    async def test_backward_compatibility_without_context_manager(self) -> None:
        """Test that operations work without using context manager (backward compat)."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        # Mock the movie endpoint
        respx.get("http://localhost:7878/api/v3/movie/1").mock(
            return_value=Response(
                200, json={"id": 1, "title": "Test Movie", "year": 2024, "tags": []}
            )
        )
        # Mock the releases endpoint
        respx.get("http://localhost:7878/api/v3/release", params={"movieId": "1"}).mock(
            return_value=Response(200, json=[])
        )

        # Call without context manager (backward compatible)
        result = await checker.check_movie(1, apply_tags=False)

        assert result is not None
        assert result.item_id == 1
        assert result.item_name == "Test Movie"


class TestExceptionHandlingInContext:
    """Tests for proper exception handling in context manager."""

    @pytest.mark.asyncio
    async def test_clients_cleaned_up_on_exception(self) -> None:
        """Test that clients are properly cleaned up when exception occurs."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock) as radarr_exit,
        ):
            radarr_enter.return_value = None

            with pytest.raises(RuntimeError, match="Test exception"):
                async with checker:
                    assert checker._radarr_client is not None
                    raise RuntimeError("Test exception")

            # pytest.raises catches the exception, so assertions below ARE reachable
            radarr_exit.assert_called_once()
            assert checker._radarr_client is None
            assert checker._in_context is False

    @pytest.mark.asyncio
    async def test_exception_info_passed_to_aexit(self) -> None:
        """Test that exception info is properly passed to __aexit__."""
        checker = ReleaseChecker(
            radarr_url="http://localhost:7878",
            radarr_api_key="test-key",
        )

        with (
            patch.object(RadarrClient, "__aenter__", new_callable=AsyncMock) as radarr_enter,
            patch.object(RadarrClient, "__aexit__", new_callable=AsyncMock) as radarr_exit,
        ):
            radarr_enter.return_value = None

            with pytest.raises(ValueError, match="Test error"):
                async with checker:
                    raise ValueError("Test error")

            # pytest.raises catches the exception, so code below IS reachable
            call_args = radarr_exit.call_args
            exc_type, exc_val, exc_tb = call_args[0]
            assert exc_type is ValueError
            assert str(exc_val) == "Test error"
            assert exc_tb is not None
