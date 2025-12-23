"""Main 4K availability checker combining Radarr and Sonarr."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient
from findarr.config import TagConfig

if TYPE_CHECKING:
    from findarr.models.common import Release
    from findarr.models.sonarr import Episode

logger = logging.getLogger(__name__)


class SamplingStrategy(Enum):
    """Strategy for sampling episodes when checking TV series for 4K.

    Attributes:
        RECENT: Check the most recent N seasons (default behavior)
        DISTRIBUTED: Check first, middle, and last seasons
        ALL: Check all seasons
    """

    RECENT = "recent"
    DISTRIBUTED = "distributed"
    ALL = "all"


@dataclass
class TagResult:
    """Result of a tag operation."""

    tag_applied: str | None = None
    tag_removed: str | None = None
    tag_created: bool = False
    tag_error: str | None = None
    dry_run: bool = False


@dataclass
class FourKResult:
    """Result of a 4K availability check."""

    item_id: int
    item_type: str  # "movie" or "series"
    has_4k: bool
    item_name: str | None = None
    releases: list[Release] = field(default_factory=list)
    episodes_checked: list[int] = field(default_factory=list)
    seasons_checked: list[int] = field(default_factory=list)
    strategy_used: SamplingStrategy | None = None
    tag_result: TagResult | None = None

    @property
    def four_k_releases(self) -> list[Release]:
        """Get only the 4K releases."""
        return [r for r in self.releases if r.is_4k()]


def select_seasons_to_check(
    available_seasons: list[int],
    strategy: SamplingStrategy,
    max_seasons: int = 3,
) -> list[int]:
    """Select which seasons to check based on strategy.

    Args:
        available_seasons: List of season numbers with aired episodes
        strategy: The sampling strategy to use
        max_seasons: Maximum number of seasons to check for RECENT strategy

    Returns:
        List of season numbers to check
    """
    if not available_seasons:
        return []

    sorted_seasons = sorted(available_seasons)

    if strategy == SamplingStrategy.ALL:
        return sorted_seasons

    if strategy == SamplingStrategy.RECENT:
        # Return the most recent N seasons
        return sorted_seasons[-max_seasons:]

    if strategy == SamplingStrategy.DISTRIBUTED:
        # Return first, middle, and last seasons
        if len(sorted_seasons) == 1:
            return sorted_seasons
        if len(sorted_seasons) == 2:
            return sorted_seasons
        # For 3+ seasons: first, middle, last
        first = sorted_seasons[0]
        last = sorted_seasons[-1]
        middle_idx = len(sorted_seasons) // 2
        middle = sorted_seasons[middle_idx]
        # Use a set to deduplicate if they overlap
        return sorted({first, middle, last})

    return sorted_seasons


class FourKChecker:
    """Check 4K availability across Radarr and Sonarr."""

    def __init__(
        self,
        radarr_url: str | None = None,
        radarr_api_key: str | None = None,
        sonarr_url: str | None = None,
        sonarr_api_key: str | None = None,
        timeout: float = 120.0,
        tag_config: TagConfig | None = None,
    ) -> None:
        """Initialize the 4K checker.

        Args:
            radarr_url: The base URL of the Radarr instance
            radarr_api_key: The Radarr API key
            sonarr_url: The base URL of the Sonarr instance
            sonarr_api_key: The Sonarr API key
            timeout: Request timeout in seconds (default 120.0)
            tag_config: Configuration for 4K tagging (optional)
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
        self._timeout = timeout
        self._tag_config = tag_config or TagConfig()

    async def check_movie(
        self,
        movie_id: int,
        *,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> FourKResult:
        """Check if a movie has 4K releases available.

        Args:
            movie_id: The Radarr movie ID
            apply_tags: Whether to apply tags to the movie (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            FourKResult with availability information

        Raises:
            ValueError: If Radarr is not configured
        """
        if not self._radarr_config:
            raise ValueError("Radarr is not configured")

        url, api_key = self._radarr_config
        async with RadarrClient(url, api_key, timeout=self._timeout) as client:
            # Get movie info for the name
            movie = await client.get_movie(movie_id)
            movie_name = movie.title if movie else None

            releases = await client.get_movie_releases(movie_id)
            has_4k = any(r.is_4k() for r in releases)

            tag_result: TagResult | None = None
            if apply_tags:
                tag_result = await self._apply_movie_tags(
                    client, movie_id, has_4k, dry_run
                )

            return FourKResult(
                item_id=movie_id,
                item_type="movie",
                has_4k=has_4k,
                item_name=movie_name,
                releases=releases,
                tag_result=tag_result,
            )

    async def _apply_movie_tags(
        self,
        client: RadarrClient,
        movie_id: int,
        has_4k: bool,
        dry_run: bool,
    ) -> TagResult:
        """Apply appropriate tags to a movie based on 4K availability.

        Args:
            client: The RadarrClient instance
            movie_id: The movie ID to tag
            has_4k: Whether the movie has 4K available
            dry_run: If True, don't actually apply tags

        Returns:
            TagResult with the operation details
        """
        tag_to_apply = (
            self._tag_config.available if has_4k else self._tag_config.unavailable
        )
        tag_to_remove = (
            self._tag_config.unavailable if has_4k else self._tag_config.available
        )

        result = TagResult(dry_run=dry_run)

        try:
            if dry_run:
                # Just report what would happen
                result.tag_applied = tag_to_apply
                result.tag_removed = tag_to_remove
                return result

            # Get existing tags ONCE to check if tag already exists
            tags = await client.get_tags()
            existing_labels = {t.label.lower(): t for t in tags}

            # Check if tag already exists before creating
            tag_already_exists = tag_to_apply.lower() in existing_labels

            if tag_already_exists:
                tag = existing_labels[tag_to_apply.lower()]
            else:
                # Create the tag since it doesn't exist
                tag = await client.create_tag(tag_to_apply)
                result.tag_created = True

            result.tag_applied = tag_to_apply

            # Apply the tag
            await client.add_tag_to_movie(movie_id, tag.id)

            # Remove the opposite tag if it exists
            if tag_to_remove.lower() in existing_labels:
                opposite_tag = existing_labels[tag_to_remove.lower()]
                await client.remove_tag_from_movie(movie_id, opposite_tag.id)
                result.tag_removed = tag_to_remove

        except Exception as e:
            logger.warning("Failed to apply tags to movie %d: %s", movie_id, e)
            result.tag_error = str(e)

        return result

    async def _apply_series_tags(
        self,
        client: SonarrClient,
        series_id: int,
        has_4k: bool,
        dry_run: bool,
    ) -> TagResult:
        """Apply appropriate tags to a series based on 4K availability.

        Args:
            client: The SonarrClient instance
            series_id: The series ID to tag
            has_4k: Whether the series has 4K available
            dry_run: If True, don't actually apply tags

        Returns:
            TagResult with the operation details
        """
        tag_to_apply = (
            self._tag_config.available if has_4k else self._tag_config.unavailable
        )
        tag_to_remove = (
            self._tag_config.unavailable if has_4k else self._tag_config.available
        )

        result = TagResult(dry_run=dry_run)

        try:
            if dry_run:
                # Just report what would happen
                result.tag_applied = tag_to_apply
                result.tag_removed = tag_to_remove
                return result

            # Get existing tags ONCE to check if tag already exists
            tags = await client.get_tags()
            existing_labels = {t.label.lower(): t for t in tags}

            # Check if tag already exists before creating
            tag_already_exists = tag_to_apply.lower() in existing_labels

            if tag_already_exists:
                tag = existing_labels[tag_to_apply.lower()]
            else:
                # Create the tag since it doesn't exist
                tag = await client.create_tag(tag_to_apply)
                result.tag_created = True

            result.tag_applied = tag_to_apply

            # Apply the tag
            await client.add_tag_to_series(series_id, tag.id)

            # Remove the opposite tag if it exists
            if tag_to_remove.lower() in existing_labels:
                opposite_tag = existing_labels[tag_to_remove.lower()]
                await client.remove_tag_from_series(series_id, opposite_tag.id)
                result.tag_removed = tag_to_remove

        except Exception as e:
            logger.warning("Failed to apply tags to series %d: %s", series_id, e)
            result.tag_error = str(e)

        return result

    async def check_movie_by_name(
        self,
        name: str,
        *,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> FourKResult:
        """Check if a movie has 4K releases available by name.

        Args:
            name: The movie title to search for
            apply_tags: Whether to apply tags to the movie (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            FourKResult with availability information

        Raises:
            ValueError: If Radarr is not configured or movie not found
        """
        if not self._radarr_config:
            raise ValueError("Radarr is not configured")

        url, api_key = self._radarr_config
        async with RadarrClient(url, api_key, timeout=self._timeout) as client:
            movie = await client.find_movie_by_name(name)
            if movie is None:
                raise ValueError(f"Movie not found: {name}")
            releases = await client.get_movie_releases(movie.id)
            has_4k = any(r.is_4k() for r in releases)

            tag_result: TagResult | None = None
            if apply_tags:
                tag_result = await self._apply_movie_tags(
                    client, movie.id, has_4k, dry_run
                )

            return FourKResult(
                item_id=movie.id,
                item_type="movie",
                has_4k=has_4k,
                item_name=movie.title,
                releases=releases,
                tag_result=tag_result,
            )

    async def search_movies(self, term: str) -> list[tuple[int, str, int]]:
        """Search for movies by title.

        Args:
            term: Search term to match against movie titles

        Returns:
            List of tuples (id, title, year) for matching movies

        Raises:
            ValueError: If Radarr is not configured
        """
        if not self._radarr_config:
            raise ValueError("Radarr is not configured")

        url, api_key = self._radarr_config
        async with RadarrClient(url, api_key, timeout=self._timeout) as client:
            movies = await client.search_movies(term)
            return [(m.id, m.title, m.year) for m in movies]

    async def check_series(
        self,
        series_id: int,
        *,
        strategy: SamplingStrategy = SamplingStrategy.RECENT,
        seasons_to_check: int = 3,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> FourKResult:
        """Check if a series has 4K releases available.

        Uses episode-level checking with configurable sampling strategy.
        First checks the latest aired episode for a quick result, then
        samples additional episodes if needed.

        Args:
            series_id: The Sonarr series ID
            strategy: The sampling strategy for selecting episodes
            seasons_to_check: Max seasons to check for RECENT strategy
            apply_tags: Whether to apply tags to the series (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            FourKResult with availability and checked episode information

        Raises:
            ValueError: If Sonarr is not configured
        """
        if not self._sonarr_config:
            raise ValueError("Sonarr is not configured")

        url, api_key = self._sonarr_config
        async with SonarrClient(url, api_key, timeout=self._timeout) as client:
            # Get series info for the name
            series = await client.get_series(series_id)
            series_name = series.title if series else None

            # Get all episodes for the series
            episodes = await client.get_episodes(series_id)
            today = date.today()

            # Filter to aired episodes
            aired_episodes = [
                e for e in episodes if e.air_date and e.air_date <= today
            ]

            if not aired_episodes:
                # No aired episodes - return empty result
                tag_result: TagResult | None = None
                if apply_tags:
                    tag_result = await self._apply_series_tags(
                        client, series_id, False, dry_run
                    )
                return FourKResult(
                    item_id=series_id,
                    item_type="series",
                    has_4k=False,
                    item_name=series_name,
                    strategy_used=strategy,
                    tag_result=tag_result,
                )

            # Group episodes by season
            episodes_by_season: dict[int, list[Episode]] = {}
            for ep in aired_episodes:
                if ep.season_number not in episodes_by_season:
                    episodes_by_season[ep.season_number] = []
                episodes_by_season[ep.season_number].append(ep)

            # Determine which seasons to check
            available_seasons = list(episodes_by_season.keys())
            seasons_to_sample = select_seasons_to_check(
                available_seasons, strategy, seasons_to_check
            )

            all_releases: list[Release] = []
            episodes_checked: list[int] = []
            seasons_checked: list[int] = []

            # For each selected season, find the latest episode and check it
            for season_num in seasons_to_sample:
                season_episodes = episodes_by_season.get(season_num, [])
                if not season_episodes:
                    continue

                # Get the latest aired episode in this season
                latest_in_season = max(
                    season_episodes, key=lambda e: e.air_date or date.min
                )

                # Check releases for this episode
                releases = await client.get_episode_releases(latest_in_season.id)
                episodes_checked.append(latest_in_season.id)
                seasons_checked.append(season_num)

                # Check if any 4K releases found
                four_k_found = any(r.is_4k() for r in releases)
                all_releases.extend(releases)

                # Short-circuit if 4K found
                if four_k_found:
                    tag_result = None
                    if apply_tags:
                        tag_result = await self._apply_series_tags(
                            client, series_id, True, dry_run
                        )
                    return FourKResult(
                        item_id=series_id,
                        item_type="series",
                        has_4k=True,
                        item_name=series_name,
                        releases=all_releases,
                        episodes_checked=episodes_checked,
                        seasons_checked=seasons_checked,
                        strategy_used=strategy,
                        tag_result=tag_result,
                    )

            # No 4K found after checking all sampled episodes
            tag_result = None
            if apply_tags:
                tag_result = await self._apply_series_tags(
                    client, series_id, False, dry_run
                )
            return FourKResult(
                item_id=series_id,
                item_type="series",
                has_4k=False,
                item_name=series_name,
                releases=all_releases,
                episodes_checked=episodes_checked,
                seasons_checked=seasons_checked,
                strategy_used=strategy,
                tag_result=tag_result,
            )

    async def check_series_by_name(
        self,
        name: str,
        *,
        strategy: SamplingStrategy = SamplingStrategy.RECENT,
        seasons_to_check: int = 3,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> FourKResult:
        """Check if a series has 4K releases available by name.

        Args:
            name: The series title to search for
            strategy: The sampling strategy for selecting episodes
            seasons_to_check: Max seasons to check for RECENT strategy
            apply_tags: Whether to apply tags to the series (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            FourKResult with availability and checked episode information

        Raises:
            ValueError: If Sonarr is not configured or series not found
        """
        if not self._sonarr_config:
            raise ValueError("Sonarr is not configured")

        url, api_key = self._sonarr_config
        async with SonarrClient(url, api_key, timeout=self._timeout) as client:
            series = await client.find_series_by_name(name)
            if series is None:
                raise ValueError(f"Series not found: {name}")

        # Now use check_series with the found ID
        return await self.check_series(
            series.id,
            strategy=strategy,
            seasons_to_check=seasons_to_check,
            apply_tags=apply_tags,
            dry_run=dry_run,
        )

    async def search_series(self, term: str) -> list[tuple[int, str, int]]:
        """Search for series by title.

        Args:
            term: Search term to match against series titles

        Returns:
            List of tuples (id, title, year) for matching series

        Raises:
            ValueError: If Sonarr is not configured
        """
        if not self._sonarr_config:
            raise ValueError("Sonarr is not configured")

        url, api_key = self._sonarr_config
        async with SonarrClient(url, api_key, timeout=self._timeout) as client:
            series_list = await client.search_series(term)
            return [(s.id, s.title, s.year) for s in series_list]
