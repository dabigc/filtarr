"""Radarr API client."""

from findarr.clients.base import BaseArrClient
from findarr.models.common import Quality, Release


class RadarrClient(BaseArrClient):
    """Client for interacting with the Radarr API.

    Inherits retry and caching functionality from BaseArrClient.

    Example:
        async with RadarrClient("http://localhost:7878", "api-key") as client:
            releases = await client.get_movie_releases(123)
            has_4k = await client.has_4k_releases(123)
    """

    async def get_movie_releases(self, movie_id: int) -> list[Release]:
        """Search for releases for a specific movie.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            List of releases found by indexers
        """
        data = await self._get("/api/v3/release", params={"movieId": movie_id})

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
