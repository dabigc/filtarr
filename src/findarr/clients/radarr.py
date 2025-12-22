"""Radarr API client."""

from typing import Any

import httpx

from findarr.models.common import Quality, Release


class RadarrClient:
    """Client for interacting with the Radarr API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        """Initialize the Radarr client.

        Args:
            base_url: The base URL of the Radarr instance (e.g., http://localhost:7878)
            api_key: The Radarr API key
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "RadarrClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not in context."""
        if self._client is None:
            raise RuntimeError("Client must be used within async context manager")
        return self._client

    async def get_movie_releases(self, movie_id: int) -> list[Release]:
        """Search for releases for a specific movie.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            List of releases found by indexers
        """
        response = await self.client.get("/api/v3/release", params={"movieId": movie_id})
        response.raise_for_status()
        data = response.json()

        releases = []
        for item in data:
            quality_data = item.get("quality", {}).get("quality", {})
            releases.append(
                Release(
                    guid=item["guid"],
                    title=item["title"],
                    indexer=item.get("indexer", "Unknown"),
                    size=item.get("size", 0),
                    quality=Quality(
                        id=quality_data.get("id", 0),
                        name=quality_data.get("name", "Unknown"),
                    ),
                )
            )
        return releases

    async def has_4k_releases(self, movie_id: int) -> bool:
        """Check if a movie has any 4K releases available.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            True if 4K releases are available
        """
        releases = await self.get_movie_releases(movie_id)
        return any(r.is_4k() for r in releases)
