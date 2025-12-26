"""Sonarr API client."""

from datetime import date
from typing import Any

from filtarr.clients.base import BaseArrClient
from filtarr.models.common import Release, Tag
from filtarr.models.sonarr import Episode, Season, Series


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
                    tags=item.get("tags", []),
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
            tags=data.get("tags", []),
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
        return [self._parse_release(item) for item in data]

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
        return [self._parse_release(item) for item in data]

    async def has_4k_releases(self, series_id: int) -> bool:
        """Check if a series has any 4K releases available.

        Args:
            series_id: The Sonarr series ID

        Returns:
            True if 4K releases are available
        """
        releases = await self.get_series_releases(series_id)
        return any(r.is_4k() for r in releases)

    # Tag management methods

    async def get_tags(self) -> list[Tag]:
        """Fetch all tags.

        Returns:
            List of Tag models
        """
        data = await self._get("/api/v3/tag")
        return [Tag.model_validate(item) for item in data]

    async def create_tag(self, label: str) -> Tag:
        """Create a new tag.

        Args:
            label: The tag label

        Returns:
            The created Tag model
        """
        data = await self._post("/api/v3/tag", json={"label": label})
        return Tag.model_validate(data)

    async def get_or_create_tag(self, label: str) -> Tag:
        """Get an existing tag by label or create it if it doesn't exist.

        Args:
            label: The tag label

        Returns:
            The existing or newly created Tag model
        """
        tags = await self.get_tags()
        for tag in tags:
            if tag.label.lower() == label.lower():
                return tag
        return await self.create_tag(label)

    async def get_series_raw(self, series_id: int) -> dict[str, Any]:
        """Fetch raw series data for updating.

        Args:
            series_id: The Sonarr series ID

        Returns:
            Raw series data dictionary
        """
        data: dict[str, Any] = await self._get(f"/api/v3/series/{series_id}")
        return data

    async def update_series(self, series_data: dict[str, Any]) -> Series:
        """Update a series.

        Args:
            series_data: The complete series data dictionary with modifications

        Returns:
            The updated Series model
        """
        series_id = series_data["id"]
        data = await self._put(f"/api/v3/series/{series_id}", json=series_data)
        # Invalidate cache for this series
        await self.invalidate_cache(f"/api/v3/series/{series_id}")
        await self.invalidate_cache("/api/v3/series")

        # Parse the response into a Series model
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
            tags=data.get("tags", []),
        )

    async def add_tag_to_series(self, series_id: int, tag_id: int) -> Series:
        """Add a tag to a series.

        Args:
            series_id: The Sonarr series ID
            tag_id: The tag ID to add

        Returns:
            The updated Series model
        """
        series_data = await self.get_series_raw(series_id)
        tags: list[int] = series_data.get("tags", [])
        if tag_id not in tags:
            tags.append(tag_id)
            series_data["tags"] = tags
            return await self.update_series(series_data)
        return await self.get_series(series_id)

    async def remove_tag_from_series(self, series_id: int, tag_id: int) -> Series:
        """Remove a tag from a series.

        Args:
            series_id: The Sonarr series ID
            tag_id: The tag ID to remove

        Returns:
            The updated Series model
        """
        series_data = await self.get_series_raw(series_id)
        tags: list[int] = series_data.get("tags", [])
        if tag_id in tags:
            tags.remove(tag_id)
            series_data["tags"] = tags
            return await self.update_series(series_data)
        return await self.get_series(series_id)

    # TaggableClient protocol methods (aliases for generic tag operations)

    async def add_tag_to_item(self, item_id: int, tag_id: int) -> Series:
        """Add a tag to an item (series).

        This is an alias for add_tag_to_series to conform to TaggableClient protocol.

        Args:
            item_id: The series ID
            tag_id: The tag ID to add

        Returns:
            The updated Series model
        """
        return await self.add_tag_to_series(item_id, tag_id)

    async def remove_tag_from_item(self, item_id: int, tag_id: int) -> Series:
        """Remove a tag from an item (series).

        This is an alias for remove_tag_from_series to conform to TaggableClient protocol.

        Args:
            item_id: The series ID
            tag_id: The tag ID to remove

        Returns:
            The updated Series model
        """
        return await self.remove_tag_from_series(item_id, tag_id)
