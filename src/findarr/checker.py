"""Main 4K availability checker combining Radarr and Sonarr."""

from dataclasses import dataclass

from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient
from findarr.models.common import Release


@dataclass
class FourKResult:
    """Result of a 4K availability check."""

    item_id: int
    item_type: str  # "movie" or "series"
    has_4k: bool
    releases: list[Release]

    @property
    def four_k_releases(self) -> list[Release]:
        """Get only the 4K releases."""
        return [r for r in self.releases if r.is_4k()]


class FourKChecker:
    """Check 4K availability across Radarr and Sonarr."""

    def __init__(
        self,
        radarr_url: str | None = None,
        radarr_api_key: str | None = None,
        sonarr_url: str | None = None,
        sonarr_api_key: str | None = None,
    ) -> None:
        """Initialize the 4K checker.

        Args:
            radarr_url: The base URL of the Radarr instance
            radarr_api_key: The Radarr API key
            sonarr_url: The base URL of the Sonarr instance
            sonarr_api_key: The Sonarr API key
        """
        self._radarr_config = (
            (radarr_url, radarr_api_key)
            if radarr_url and radarr_api_key
            else None
        )
        self._sonarr_config = (
            (sonarr_url, sonarr_api_key)
            if sonarr_url and sonarr_api_key
            else None
        )

    async def check_movie(self, movie_id: int) -> FourKResult:
        """Check if a movie has 4K releases available.

        Args:
            movie_id: The Radarr movie ID

        Returns:
            FourKResult with availability information

        Raises:
            ValueError: If Radarr is not configured
        """
        if not self._radarr_config:
            raise ValueError("Radarr is not configured")

        url, api_key = self._radarr_config
        async with RadarrClient(url, api_key) as client:
            releases = await client.get_movie_releases(movie_id)
            return FourKResult(
                item_id=movie_id,
                item_type="movie",
                has_4k=any(r.is_4k() for r in releases),
                releases=releases,
            )

    async def check_series(self, series_id: int) -> FourKResult:
        """Check if a series has 4K releases available.

        Args:
            series_id: The Sonarr series ID

        Returns:
            FourKResult with availability information

        Raises:
            ValueError: If Sonarr is not configured
        """
        if not self._sonarr_config:
            raise ValueError("Sonarr is not configured")

        url, api_key = self._sonarr_config
        async with SonarrClient(url, api_key) as client:
            releases = await client.get_series_releases(series_id)
            return FourKResult(
                item_id=series_id,
                item_type="series",
                has_4k=any(r.is_4k() for r in releases),
                releases=releases,
            )
