"""Sonarr API client."""

from typing import Any

import httpx

from findarr.models.common import Quality, Release


class SonarrClient:
    """Client for interacting with the Sonarr API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        """Initialize the Sonarr client.

        Args:
            base_url: The base URL of the Sonarr instance (e.g., http://localhost:8989)
            api_key: The Sonarr API key
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "SonarrClient":
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

    async def get_series_releases(self, series_id: int) -> list[Release]:
        """Search for releases for a specific series.

        Args:
            series_id: The Sonarr series ID

        Returns:
            List of releases found by indexers
        """
        response = await self.client.get("/api/v3/release", params={"seriesId": series_id})
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

    async def has_4k_releases(self, series_id: int) -> bool:
        """Check if a series has any 4K releases available.

        Args:
            series_id: The Sonarr series ID

        Returns:
            True if 4K releases are available
        """
        releases = await self.get_series_releases(series_id)
        return any(r.is_4k() for r in releases)
