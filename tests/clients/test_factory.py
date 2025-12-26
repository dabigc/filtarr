"""Tests for ClientFactory."""

import pytest

from filtarr.clients import BaseArrClient, ClientFactory, RadarrClient, SonarrClient


class TestClientFactory:
    """Tests for ClientFactory.create()."""

    def test_create_radarr_client(self) -> None:
        """Should create RadarrClient for 'radarr' type."""
        client = ClientFactory.create("radarr", "http://localhost:7878", "test-api-key")

        assert isinstance(client, RadarrClient)
        assert isinstance(client, BaseArrClient)
        assert client.base_url == "http://localhost:7878"
        assert client.api_key == "test-api-key"

    def test_create_sonarr_client(self) -> None:
        """Should create SonarrClient for 'sonarr' type."""
        client = ClientFactory.create("sonarr", "http://localhost:8989", "test-api-key")

        assert isinstance(client, SonarrClient)
        assert isinstance(client, BaseArrClient)
        assert client.base_url == "http://localhost:8989"
        assert client.api_key == "test-api-key"

    def test_create_with_trailing_slash(self) -> None:
        """Should strip trailing slash from URL."""
        client = ClientFactory.create("radarr", "http://localhost:7878/", "test-api-key")

        assert client.base_url == "http://localhost:7878"

    def test_create_with_custom_timeout(self) -> None:
        """Should pass timeout parameter to client."""
        client = ClientFactory.create(
            "radarr", "http://localhost:7878", "test-api-key", timeout=60.0
        )

        assert client.timeout == 60.0

    def test_create_with_cache_ttl(self) -> None:
        """Should pass cache_ttl parameter to client."""
        client = ClientFactory.create(
            "sonarr", "http://localhost:8989", "test-api-key", cache_ttl=600
        )

        assert client.cache_ttl == 600

    def test_create_with_max_retries(self) -> None:
        """Should pass max_retries parameter to client."""
        client = ClientFactory.create(
            "radarr", "http://localhost:7878", "test-api-key", max_retries=5
        )

        assert client.max_retries == 5

    def test_create_with_multiple_kwargs(self) -> None:
        """Should pass multiple kwargs to client."""
        client = ClientFactory.create(
            "radarr",
            "http://localhost:7878",
            "test-api-key",
            timeout=30.0,
            cache_ttl=120,
            max_retries=2,
        )

        assert client.timeout == 30.0
        assert client.cache_ttl == 120
        assert client.max_retries == 2

    def test_create_unknown_type_raises_error(self) -> None:
        """Should raise ValueError for unknown client type."""
        with pytest.raises(ValueError, match="Unknown client type: invalid"):
            ClientFactory.create(
                "invalid",  # type: ignore[arg-type]
                "http://localhost:7878",
                "test-api-key",
            )

    def test_create_returns_base_arr_client_type(self) -> None:
        """Return type should be BaseArrClient for type narrowing."""
        # This test verifies the return type annotation works correctly
        client: BaseArrClient = ClientFactory.create(
            "radarr", "http://localhost:7878", "test-api-key"
        )

        assert isinstance(client, BaseArrClient)


class TestClientFactoryContextManager:
    """Tests for using factory-created clients as context managers."""

    @pytest.mark.asyncio
    async def test_radarr_client_as_context_manager(self) -> None:
        """Factory-created RadarrClient should work as async context manager."""
        client = ClientFactory.create("radarr", "http://localhost:7878", "test-api-key")

        # Should enter and exit context without error
        async with client:
            assert client._client is not None

        # After exiting, client should be closed
        assert client._client is None

    @pytest.mark.asyncio
    async def test_sonarr_client_as_context_manager(self) -> None:
        """Factory-created SonarrClient should work as async context manager."""
        client = ClientFactory.create("sonarr", "http://localhost:8989", "test-api-key")

        # Should enter and exit context without error
        async with client:
            assert client._client is not None

        # After exiting, client should be closed
        assert client._client is None
