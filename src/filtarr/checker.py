"""Main release checker combining Radarr and Sonarr.

This module provides connection pooling for efficient reuse of HTTP clients
across multiple check operations. Use ReleaseChecker as an async context manager
for optimal performance when making multiple API calls:

    async with ReleaseChecker(...) as checker:
        result1 = await checker.check_movie(123)
        result2 = await checker.check_movie(456)  # Reuses same HTTP connection

For single operations, ReleaseChecker also supports standalone usage with
lazy client creation (creates/destroys client per operation).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import ValidationError

from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient
from filtarr.config import TagConfig
from filtarr.criteria import (
    MOVIE_ONLY_CRITERIA,
    ResultType,
    SearchCriteria,
    get_matcher_for_criteria,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from typing import Self

    from filtarr.models.common import Release, Tag
    from filtarr.models.sonarr import Episode

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
class SearchResult:
    """Result of a release search/availability check."""

    item_id: int
    item_type: str  # "movie" or "series"
    has_match: bool
    result_type: ResultType = ResultType.FOUR_K
    item_name: str | None = None
    releases: list[Release] = field(default_factory=list)
    episodes_checked: list[int] = field(default_factory=list)
    seasons_checked: list[int] = field(default_factory=list)
    strategy_used: SamplingStrategy | None = None
    tag_result: TagResult | None = None
    _criteria: SearchCriteria | Callable[[Release], bool] | None = field(default=None, repr=False)

    @property
    def matched_releases(self) -> list[Release]:
        """Get only the releases that match the search criteria."""
        if self._criteria is None:
            # Default to 4K for backward compatibility
            return [r for r in self.releases if r.is_4k()]
        if isinstance(self._criteria, SearchCriteria):
            matcher = get_matcher_for_criteria(self._criteria)
            return [r for r in self.releases if matcher(r)]
        return [r for r in self.releases if self._criteria(r)]

    # Backward compatibility aliases
    @property
    def has_4k(self) -> bool:
        """Alias for has_match when searching for 4K."""
        return self.has_match

    @property
    def four_k_releases(self) -> list[Release]:
        """Alias for matched_releases (backward compatibility)."""
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


class ReleaseChecker:
    """Check release availability across Radarr and Sonarr.

    Supports searching for various release criteria including 4K, HDR,
    Director's Cut, and custom criteria via callables.

    This class can be used as an async context manager for connection pooling,
    which reuses HTTP clients across multiple operations:

        async with ReleaseChecker(...) as checker:
            result1 = await checker.check_movie(123)
            result2 = await checker.check_movie(456)

    It also supports standalone usage for backward compatibility, where clients
    are created and destroyed per operation.
    """

    def __init__(
        self,
        radarr_url: str | None = None,
        radarr_api_key: str | None = None,
        sonarr_url: str | None = None,
        sonarr_api_key: str | None = None,
        timeout: float = 120.0,
        tag_config: TagConfig | None = None,
    ) -> None:
        """Initialize the release checker.

        Args:
            radarr_url: The base URL of the Radarr instance
            radarr_api_key: The Radarr API key
            sonarr_url: The base URL of the Sonarr instance
            sonarr_api_key: The Sonarr API key
            timeout: Request timeout in seconds (default 120.0)
            tag_config: Configuration for tagging (optional)
        """
        self._radarr_config = (
            (radarr_url, radarr_api_key) if radarr_url and radarr_api_key else None
        )
        self._sonarr_config = (
            (sonarr_url, sonarr_api_key) if sonarr_url and sonarr_api_key else None
        )
        self._timeout = timeout
        self._tag_config = tag_config or TagConfig()
        self._tag_cache: dict[str, list[Tag]] | None = None

        # Connection pooling: store client instances for reuse
        self._radarr_client: RadarrClient | None = None
        self._sonarr_client: SonarrClient | None = None
        self._in_context: bool = False

    async def __aenter__(self) -> Self:
        """Enter async context manager, initializing pooled clients.

        When used as a context manager, clients are created once and reused
        across all operations, providing connection pooling benefits.
        """
        self._in_context = True

        if self._radarr_config:
            url, api_key = self._radarr_config
            self._radarr_client = RadarrClient(url, api_key, timeout=self._timeout)
            await self._radarr_client.__aenter__()

        if self._sonarr_config:
            url, api_key = self._sonarr_config
            self._sonarr_client = SonarrClient(url, api_key, timeout=self._timeout)
            await self._sonarr_client.__aenter__()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager, cleaning up pooled clients."""
        self._in_context = False

        if self._radarr_client:
            await self._radarr_client.__aexit__(exc_type, exc_val, exc_tb)
            self._radarr_client = None

        if self._sonarr_client:
            await self._sonarr_client.__aexit__(exc_type, exc_val, exc_tb)
            self._sonarr_client = None

        # Clear tag cache when exiting context
        self._tag_cache = None

    @asynccontextmanager
    async def _get_radarr_client(self) -> AsyncIterator[RadarrClient]:
        """Get a Radarr client, using pooled client if in context.

        When used within an async context manager, returns the pooled client.
        Otherwise, creates a temporary client for the operation.

        Yields:
            RadarrClient instance
        """
        if self._in_context and self._radarr_client:
            # Use pooled client
            yield self._radarr_client
        else:
            # Create temporary client (backward compatibility)
            if not self._radarr_config:
                raise ValueError("Radarr is not configured")
            url, api_key = self._radarr_config
            async with RadarrClient(url, api_key, timeout=self._timeout) as client:
                yield client

    @asynccontextmanager
    async def _get_sonarr_client(self) -> AsyncIterator[SonarrClient]:
        """Get a Sonarr client, using pooled client if in context.

        When used within an async context manager, returns the pooled client.
        Otherwise, creates a temporary client for the operation.

        Yields:
            SonarrClient instance
        """
        if self._in_context and self._sonarr_client:
            # Use pooled client
            yield self._sonarr_client
        else:
            # Create temporary client (backward compatibility)
            if not self._sonarr_config:
                raise ValueError("Sonarr is not configured")
            url, api_key = self._sonarr_config
            async with SonarrClient(url, api_key, timeout=self._timeout) as client:
                yield client

    async def _get_cached_tags(
        self, client: RadarrClient | SonarrClient, cache_key: str
    ) -> list[Tag]:
        """Get tags from cache or fetch from client.

        Tags are cached per client type (radarr/sonarr) to avoid repeated
        API calls when processing batches of items.

        Args:
            client: The RadarrClient or SonarrClient instance
            cache_key: Key for caching ("radarr" or "sonarr")

        Returns:
            List of Tag models
        """
        if self._tag_cache is None:
            self._tag_cache = {}
        if cache_key not in self._tag_cache:
            self._tag_cache[cache_key] = await client.get_tags()
        return self._tag_cache[cache_key]

    def clear_tag_cache(self) -> None:
        """Clear the tag cache.

        Call this method when you need to refresh tag data, for example
        after creating new tags or if tags may have been modified externally.
        """
        self._tag_cache = None

    async def check_movie(
        self,
        movie_id: int,
        *,
        criteria: SearchCriteria | Callable[[Release], bool] = SearchCriteria.FOUR_K,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> SearchResult:
        """Check if a movie has releases matching the criteria.

        Args:
            movie_id: The Radarr movie ID
            criteria: Search criteria - either a SearchCriteria enum or custom callable
            apply_tags: Whether to apply tags to the movie (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            SearchResult with availability information

        Raises:
            ValueError: If Radarr is not configured
        """
        if not self._radarr_config:
            raise ValueError("Radarr is not configured")

        async with self._get_radarr_client() as client:
            # Get movie info for the name
            movie = await client.get_movie(movie_id)
            movie_name = movie.title if movie else None

            releases = await client.get_movie_releases(movie_id)

            # Determine matcher based on criteria
            if isinstance(criteria, SearchCriteria):
                matcher = get_matcher_for_criteria(criteria)
                result_type = ResultType(criteria.value)
            else:
                matcher = criteria
                result_type = ResultType.CUSTOM

            has_match = any(matcher(r) for r in releases)

            tag_result: TagResult | None = None
            if apply_tags:
                # Only pass criteria to tagging if it's a SearchCriteria enum
                tag_criteria = (
                    criteria if isinstance(criteria, SearchCriteria) else SearchCriteria.FOUR_K
                )
                tag_result = await self._apply_movie_tags(
                    client, movie_id, has_match, dry_run, tag_criteria
                )

            return SearchResult(
                item_id=movie_id,
                item_type="movie",
                has_match=has_match,
                result_type=result_type,
                item_name=movie_name,
                releases=releases,
                tag_result=tag_result,
                _criteria=criteria,
            )

    async def _apply_movie_tags(
        self,
        client: RadarrClient,
        movie_id: int,
        has_match: bool,
        dry_run: bool,
        criteria: SearchCriteria = SearchCriteria.FOUR_K,
    ) -> TagResult:
        """Apply appropriate tags to a movie based on release availability.

        Args:
            client: The RadarrClient instance
            movie_id: The movie ID to tag
            has_match: Whether the movie has matching releases available
            dry_run: If True, don't actually apply tags
            criteria: The search criteria used (determines tag names)

        Returns:
            TagResult with the operation details
        """
        available_tag, unavailable_tag = self._tag_config.get_tag_names(criteria.value)
        tag_to_apply = available_tag if has_match else unavailable_tag
        tag_to_remove = unavailable_tag if has_match else available_tag

        result = TagResult(dry_run=dry_run)

        try:
            if dry_run:
                # Just report what would happen
                result.tag_applied = tag_to_apply
                result.tag_removed = tag_to_remove
                return result

            # Get existing tags from cache (or fetch once per batch)
            tags = await self._get_cached_tags(client, "radarr")
            existing_labels = {t.label.lower(): t for t in tags}

            # Check if tag already exists before creating
            tag_already_exists = tag_to_apply.lower() in existing_labels

            if tag_already_exists:
                tag = existing_labels[tag_to_apply.lower()]
            else:
                # Create the tag since it doesn't exist
                tag = await client.create_tag(tag_to_apply)
                result.tag_created = True
                # Update cache with the new tag
                if self._tag_cache is not None and "radarr" in self._tag_cache:
                    self._tag_cache["radarr"].append(tag)

            result.tag_applied = tag_to_apply

            # Apply the tag
            await client.add_tag_to_movie(movie_id, tag.id)

            # Remove the opposite tag if it exists
            if tag_to_remove.lower() in existing_labels:
                opposite_tag = existing_labels[tag_to_remove.lower()]
                await client.remove_tag_from_movie(movie_id, opposite_tag.id)
                result.tag_removed = tag_to_remove

        except httpx.HTTPStatusError as e:
            logger.warning(
                "HTTP error applying tags to movie %d: %s %s",
                movie_id,
                e.response.status_code,
                e.response.reason_phrase,
            )
            result.tag_error = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("Network error applying tags to movie %d: %s", movie_id, e)
            result.tag_error = f"Network error: {e}"
        except ValidationError as e:
            logger.warning("Validation error applying tags to movie %d: %s", movie_id, e)
            result.tag_error = f"Validation error: {e}"

        return result

    async def _apply_series_tags(
        self,
        client: SonarrClient,
        series_id: int,
        has_match: bool,
        dry_run: bool,
        criteria: SearchCriteria = SearchCriteria.FOUR_K,
    ) -> TagResult:
        """Apply appropriate tags to a series based on release availability.

        Args:
            client: The SonarrClient instance
            series_id: The series ID to tag
            has_match: Whether the series has matching releases available
            dry_run: If True, don't actually apply tags
            criteria: The search criteria used (determines tag names)

        Returns:
            TagResult with the operation details
        """
        available_tag, unavailable_tag = self._tag_config.get_tag_names(criteria.value)
        tag_to_apply = available_tag if has_match else unavailable_tag
        tag_to_remove = unavailable_tag if has_match else available_tag

        result = TagResult(dry_run=dry_run)

        try:
            if dry_run:
                # Just report what would happen
                result.tag_applied = tag_to_apply
                result.tag_removed = tag_to_remove
                return result

            # Get existing tags from cache (or fetch once per batch)
            tags = await self._get_cached_tags(client, "sonarr")
            existing_labels = {t.label.lower(): t for t in tags}

            # Check if tag already exists before creating
            tag_already_exists = tag_to_apply.lower() in existing_labels

            if tag_already_exists:
                tag = existing_labels[tag_to_apply.lower()]
            else:
                # Create the tag since it doesn't exist
                tag = await client.create_tag(tag_to_apply)
                result.tag_created = True
                # Update cache with the new tag
                if self._tag_cache is not None and "sonarr" in self._tag_cache:
                    self._tag_cache["sonarr"].append(tag)

            result.tag_applied = tag_to_apply

            # Apply the tag
            await client.add_tag_to_series(series_id, tag.id)

            # Remove the opposite tag if it exists
            if tag_to_remove.lower() in existing_labels:
                opposite_tag = existing_labels[tag_to_remove.lower()]
                await client.remove_tag_from_series(series_id, opposite_tag.id)
                result.tag_removed = tag_to_remove

        except httpx.HTTPStatusError as e:
            logger.warning(
                "HTTP error applying tags to series %d: %s %s",
                series_id,
                e.response.status_code,
                e.response.reason_phrase,
            )
            result.tag_error = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("Network error applying tags to series %d: %s", series_id, e)
            result.tag_error = f"Network error: {e}"
        except ValidationError as e:
            logger.warning("Validation error applying tags to series %d: %s", series_id, e)
            result.tag_error = f"Validation error: {e}"

        return result

    async def check_movie_by_name(
        self,
        name: str,
        *,
        criteria: SearchCriteria | Callable[[Release], bool] = SearchCriteria.FOUR_K,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> SearchResult:
        """Check if a movie has releases matching criteria by name.

        Args:
            name: The movie title to search for
            criteria: Search criteria - either a SearchCriteria enum or custom callable
            apply_tags: Whether to apply tags to the movie (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            SearchResult with availability information

        Raises:
            ValueError: If Radarr is not configured or movie not found
        """
        if not self._radarr_config:
            raise ValueError("Radarr is not configured")

        async with self._get_radarr_client() as client:
            movie = await client.find_movie_by_name(name)
            if movie is None:
                raise ValueError(f"Movie not found: {name}")
            releases = await client.get_movie_releases(movie.id)

            # Determine matcher based on criteria
            if isinstance(criteria, SearchCriteria):
                matcher = get_matcher_for_criteria(criteria)
                result_type = ResultType(criteria.value)
            else:
                matcher = criteria
                result_type = ResultType.CUSTOM

            has_match = any(matcher(r) for r in releases)

            tag_result: TagResult | None = None
            if apply_tags:
                # Only pass criteria to tagging if it's a SearchCriteria enum
                tag_criteria = (
                    criteria if isinstance(criteria, SearchCriteria) else SearchCriteria.FOUR_K
                )
                tag_result = await self._apply_movie_tags(
                    client, movie.id, has_match, dry_run, tag_criteria
                )

            return SearchResult(
                item_id=movie.id,
                item_type="movie",
                has_match=has_match,
                result_type=result_type,
                item_name=movie.title,
                releases=releases,
                tag_result=tag_result,
                _criteria=criteria,
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

        async with self._get_radarr_client() as client:
            movies = await client.search_movies(term)
            return [(m.id, m.title, m.year) for m in movies]

    async def check_series(
        self,
        series_id: int,
        *,
        criteria: SearchCriteria | Callable[[Release], bool] = SearchCriteria.FOUR_K,
        strategy: SamplingStrategy = SamplingStrategy.RECENT,
        seasons_to_check: int = 3,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> SearchResult:
        """Check if a series has releases matching the criteria.

        Uses episode-level checking with configurable sampling strategy.
        First checks the latest aired episode for a quick result, then
        samples additional episodes if needed.

        Args:
            series_id: The Sonarr series ID
            criteria: Search criteria - either a SearchCriteria enum or custom callable
            strategy: The sampling strategy for selecting episodes
            seasons_to_check: Max seasons to check for RECENT strategy
            apply_tags: Whether to apply tags to the series (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            SearchResult with availability and checked episode information

        Raises:
            ValueError: If Sonarr is not configured or if movie-only criteria is used
        """
        if not self._sonarr_config:
            raise ValueError("Sonarr is not configured")

        # Enforce movie-only criteria restriction
        if isinstance(criteria, SearchCriteria) and criteria in MOVIE_ONLY_CRITERIA:
            raise ValueError(
                f"{criteria.name} criteria is only applicable to movies, not TV series"
            )

        # Determine matcher based on criteria
        if isinstance(criteria, SearchCriteria):
            matcher = get_matcher_for_criteria(criteria)
            result_type = ResultType(criteria.value)
        else:
            matcher = criteria
            result_type = ResultType.CUSTOM

        async with self._get_sonarr_client() as client:
            # Get series info for the name
            series = await client.get_series(series_id)
            series_name = series.title if series else None

            # Get all episodes for the series
            episodes = await client.get_episodes(series_id)
            today = date.today()

            # Filter to aired episodes
            aired_episodes = [e for e in episodes if e.air_date and e.air_date <= today]

            if not aired_episodes:
                # No aired episodes - return empty result
                tag_result: TagResult | None = None
                if apply_tags:
                    tag_criteria = (
                        criteria if isinstance(criteria, SearchCriteria) else SearchCriteria.FOUR_K
                    )
                    tag_result = await self._apply_series_tags(
                        client, series_id, False, dry_run, tag_criteria
                    )
                return SearchResult(
                    item_id=series_id,
                    item_type="series",
                    has_match=False,
                    result_type=result_type,
                    item_name=series_name,
                    strategy_used=strategy,
                    tag_result=tag_result,
                    _criteria=criteria,
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
                latest_in_season = max(season_episodes, key=lambda e: e.air_date or date.min)

                # Check releases for this episode
                releases = await client.get_episode_releases(latest_in_season.id)
                episodes_checked.append(latest_in_season.id)
                seasons_checked.append(season_num)

                # Check if any matching releases found
                match_found = any(matcher(r) for r in releases)
                all_releases.extend(releases)

                # Short-circuit if match found
                if match_found:
                    tag_result = None
                    if apply_tags:
                        tag_criteria = (
                            criteria
                            if isinstance(criteria, SearchCriteria)
                            else SearchCriteria.FOUR_K
                        )
                        tag_result = await self._apply_series_tags(
                            client, series_id, True, dry_run, tag_criteria
                        )
                    return SearchResult(
                        item_id=series_id,
                        item_type="series",
                        has_match=True,
                        result_type=result_type,
                        item_name=series_name,
                        releases=all_releases,
                        episodes_checked=episodes_checked,
                        seasons_checked=seasons_checked,
                        strategy_used=strategy,
                        tag_result=tag_result,
                        _criteria=criteria,
                    )

            # No match found after checking all sampled episodes
            tag_result = None
            if apply_tags:
                tag_criteria = (
                    criteria if isinstance(criteria, SearchCriteria) else SearchCriteria.FOUR_K
                )
                tag_result = await self._apply_series_tags(
                    client, series_id, False, dry_run, tag_criteria
                )
            return SearchResult(
                item_id=series_id,
                item_type="series",
                has_match=False,
                result_type=result_type,
                item_name=series_name,
                releases=all_releases,
                episodes_checked=episodes_checked,
                seasons_checked=seasons_checked,
                strategy_used=strategy,
                tag_result=tag_result,
                _criteria=criteria,
            )

    async def check_series_by_name(
        self,
        name: str,
        *,
        criteria: SearchCriteria | Callable[[Release], bool] = SearchCriteria.FOUR_K,
        strategy: SamplingStrategy = SamplingStrategy.RECENT,
        seasons_to_check: int = 3,
        apply_tags: bool = True,
        dry_run: bool = False,
    ) -> SearchResult:
        """Check if a series has releases matching criteria by name.

        Args:
            name: The series title to search for
            criteria: Search criteria - either a SearchCriteria enum or custom callable
            strategy: The sampling strategy for selecting episodes
            seasons_to_check: Max seasons to check for RECENT strategy
            apply_tags: Whether to apply tags to the series (default True)
            dry_run: If True, don't actually apply tags (default False)

        Returns:
            SearchResult with availability and checked episode information

        Raises:
            ValueError: If Sonarr is not configured, series not found, or movie-only criteria
        """
        if not self._sonarr_config:
            raise ValueError("Sonarr is not configured")

        # Enforce movie-only criteria restriction
        if isinstance(criteria, SearchCriteria) and criteria in MOVIE_ONLY_CRITERIA:
            raise ValueError(
                f"{criteria.name} criteria is only applicable to movies, not TV series"
            )

        async with self._get_sonarr_client() as client:
            series = await client.find_series_by_name(name)
            if series is None:
                raise ValueError(f"Series not found: {name}")

        # Now use check_series with the found ID
        return await self.check_series(
            series.id,
            criteria=criteria,
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

        async with self._get_sonarr_client() as client:
            series_list = await client.search_series(term)
            return [(s.id, s.title, s.year) for s in series_list]
