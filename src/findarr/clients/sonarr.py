"""Sonarr API client."""

from datetime import date

from findarr.clients.base import BaseArrClient
from findarr.models.common import Quality, Release
from findarr.models.sonarr import Episode, Season, Series


class SonarrClient(BaseArrClient):
    """Client for interacting with the Sonarr API.

    Inherits retry and caching functionality from BaseArrClient.

    Example:
        async with SonarrClient("http://localhost:8989", "api-key") as client:
            series = await client.get_series(456)
            episodes = await client.get_episodes(456)
            latest = await client.get_latest_aired_episode(456)
            releases = await client.get_episode_releases(latest.id)
            matches = await client.search_series("Breaking Bad")
    """

    async def get_all_series(self) -> list[Series]:
        """Fetch all series in the library.

        Returns:
            List of Series models
        """
        data = await self._get("/api/v3/series")
        series_list = []
        for item in data:
            seasons = []
            for s in item.get("seasons", []):
                stats = s.get("statistics", {})
                seasons.append(
                    Season(
                        seasonNumber=s.get("seasonNumber", 0),
                        monitored=s.get("monitored", True),
                        **{
                            "statistics.episodeCount": stats.get("episodeCount", 0),
                            "statistics.episodeFileCount": stats.get("episodeFileCount", 0),
                        },
                    )
                )
            series_list.append(
                Series(
                    id=item["id"],
                    title=item.get("title", ""),
                    year=item.get("year", 0),
                    seasons=seasons,
                    monitored=item.get("monitored", True),
                )
            )
        return series_list

    async def search_series(self, term: str) -> list[Series]:
        """Search for series in the library by title.

        Args:
            term: Search term to match against series titles

        Returns:
            List of matching Series models
        """
        all_series = await self.get_all_series()
        term_lower = term.lower()
        return [s for s in all_series if term_lower in s.title.lower()]

    async def find_series_by_name(self, name: str) -> Series | None:
        """Find a series by exact or partial name match.

        If multiple series match, returns the one with the closest title match.
        For exact matches, returns immediately.

        Args:
            name: Series name to search for

        Returns:
            Series if found, None otherwise
        """
        series_list = await self.search_series(name)
        if not series_list:
            return None

        # Check for exact match first (case-insensitive)
        name_lower = name.lower()
        for series in series_list:
            if series.title.lower() == name_lower:
                return series

        # Return the series with the shortest title (closest match)
        return min(series_list, key=lambda s: len(s.title))

    async def get_series(self, series_id: int) -> Series:
        """Fetch series metadata including seasons.

        Args:
            series_id: The Sonarr series ID

        Returns:
            Series model with seasons list
        """
        data = await self._get(f"/api/v3/series/{series_id}")

        seasons = []
        for s in data.get("seasons", []):
            stats = s.get("statistics", {})
            seasons.append(
                Season(
                    seasonNumber=s.get("seasonNumber", 0),
                    monitored=s.get("monitored", True),
                    **{
                        "statistics.episodeCount": stats.get("episodeCount", 0),
                        "statistics.episodeFileCount": stats.get("episodeFileCount", 0),
                    },
                )
            )

        return Series(
            id=data["id"],
            title=data.get("title", ""),
            year=data.get("year", 0),
            seasons=seasons,
            monitored=data.get("monitored", True),
        )

    async def get_episodes(
        self, series_id: int, *, season_number: int | None = None
    ) -> list[Episode]:
        """Fetch all episodes for a series.

        Args:
            series_id: The Sonarr series ID
            season_number: Optional season filter

        Returns:
            List of Episode models
        """
        params: dict[str, int] = {"seriesId": series_id}
        if season_number is not None:
            params["seasonNumber"] = season_number

        data = await self._get("/api/v3/episode", params=params)

        episodes = []
        for item in data:
            episodes.append(Episode.model_validate(item))
        return episodes

    async def get_episode_releases(self, episode_id: int) -> list[Release]:
        """Fetch releases for a specific episode.

        Args:
            episode_id: The Sonarr episode ID

        Returns:
            List of releases found by indexers
        """
        data = await self._get("/api/v3/release", params={"episodeId": episode_id})

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

    async def get_latest_aired_episode(self, series_id: int) -> Episode | None:
        """Find the most recently aired episode.

        Args:
            series_id: The Sonarr series ID

        Returns:
            The most recently aired episode, or None if no episodes have aired
        """
        episodes = await self.get_episodes(series_id)
        today = date.today()

        # Filter to episodes that have aired (air_date <= today)
        aired_episodes = [e for e in episodes if e.air_date and e.air_date <= today]

        if not aired_episodes:
            return None

        # Return the one with the most recent air date
        return max(aired_episodes, key=lambda e: e.air_date or date.min)

    async def get_series_releases(self, series_id: int) -> list[Release]:
        """Search for releases for a specific series.

        Args:
            series_id: The Sonarr series ID

        Returns:
            List of releases found by indexers
        """
        data = await self._get("/api/v3/release", params={"seriesId": series_id})

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
