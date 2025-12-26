"""Factory for creating Arr client instances."""

from typing import Literal

from filtarr.clients.base import BaseArrClient
from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient


class ClientFactory:
    """Factory for creating Arr client instances.

    This factory provides a unified interface for creating Radarr and Sonarr
    clients based on a client type string. This is useful for dynamic client
    creation based on configuration or user input.

    Example:
        # Create a Radarr client
        client = ClientFactory.create("radarr", "http://localhost:7878", "api-key")

        # Create a Sonarr client with custom timeout
        client = ClientFactory.create(
            "sonarr",
            "http://localhost:8989",
            "api-key",
            timeout=60.0
        )
    """

    @staticmethod
    def create(
        client_type: Literal["radarr", "sonarr"],
        url: str,
        api_key: str,
        *,
        timeout: float = 120.0,
        cache_ttl: int = 300,
        max_retries: int = 3,
    ) -> BaseArrClient:
        """Create an Arr client instance based on type.

        Args:
            client_type: The type of client to create ("radarr" or "sonarr")
            url: The base URL of the Arr instance
            api_key: The API key for authentication
            timeout: Request timeout in seconds (default 120.0)
            cache_ttl: Cache time-to-live in seconds (default 300)
            max_retries: Maximum number of retry attempts (default 3)

        Returns:
            An instance of RadarrClient or SonarrClient

        Raises:
            ValueError: If client_type is not "radarr" or "sonarr"

        Example:
            async with ClientFactory.create("radarr", url, api_key) as client:
                releases = await client.get_movie_releases(123)
        """
        if client_type == "radarr":
            return RadarrClient(
                url, api_key, timeout=timeout, cache_ttl=cache_ttl, max_retries=max_retries
            )
        elif client_type == "sonarr":
            return SonarrClient(
                url, api_key, timeout=timeout, cache_ttl=cache_ttl, max_retries=max_retries
            )
        else:
            raise ValueError(f"Unknown client type: {client_type}")
