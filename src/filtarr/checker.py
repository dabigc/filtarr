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

from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient
from filtarr.config import TagConfig
from filtarr.criteria import (
    MOVIE_ONLY_CRITERIA,
    ResultType,
    SearchCriteria,
    get_matcher_for_criteria,
)
from filtarr.tagger import ReleaseTagger, TagResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from typing import Self

    from filtarr.models.common import Release
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
        tagger: ReleaseTagger | None = None,
    ) -> None:
        """Initialize the release checker.

        Args:
            radarr_url: The base URL of the Radarr instance
            radarr_api_key: The Radarr API key
            sonarr_url: The base URL of the Sonarr instance
            sonarr_api_key: The Sonarr API key
            timeout: Request timeout in seconds (default 120.0)
            tag_config: Configuration for tagging (optional)
            tagger: Custom ReleaseTagger instance (optional, created from tag_config if not provided)
        """
        self._radarr_config = (
            (radarr_url, radarr_api_key) if radarr_url and radarr_api_key else None
        )
        self._sonarr_config = (
            (sonarr_url, sonarr_api_key) if sonarr_url and sonarr_api_key else None
        )
        self._timeout = timeout
        self._tag_config = tag_config or TagConfig()
        self._tagger = tagger or ReleaseTagger(self._tag_config)

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
        self._tagger.clear_tag_cache()

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

    def clear_tag_cache(self) -> None:
        """Clear the tag cache.

        Call this method when you need to refresh tag data, for example
        after creating new tags or if tags may have been modified externally.
        """
        self._tagger.clear_tag_cache()

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
                tag_result = await self._tagger.apply_movie_tags(
                    client, movie_id, has_match, tag_criteria, dry_run
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
                tag_result = await self._tagger.apply_movie_tags(
                    client, movie.id, has_match, tag_criteria, dry_run
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
                    tag_result = await self._tagger.apply_series_tags(
                        client, series_id, False, tag_criteria, dry_run
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
            for episode in aired_episodes:
                if episode.season_number not in episodes_by_season:
                    episodes_by_season[episode.season_number] = []
                episodes_by_season[episode.season_number].append(episode)

            # Determine which seasons to check
            available_seasons = list(episodes_by_season.keys())
            seasons_to_sample = select_seasons_to_check(
                available_seasons, strategy, seasons_to_check
            )

            all_releases: list[Release] = []
            episodes_checked: list[int] = []
            seasons_checked: list[int] = []

            # For each selected season, find the latest episode and check it
            for season_number in seasons_to_sample:
                season_episodes = episodes_by_season.get(season_number, [])
                if not season_episodes:
                    continue

                # Get the latest aired episode in this season
                latest_in_season = max(season_episodes, key=lambda e: e.air_date or date.min)

                # Check releases for this episode
                releases = await client.get_episode_releases(latest_in_season.id)
                episodes_checked.append(latest_in_season.id)
                seasons_checked.append(season_number)

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
                        tag_result = await self._tagger.apply_series_tags(
                            client, series_id, True, tag_criteria, dry_run
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
                tag_result = await self._tagger.apply_series_tags(
                    client, series_id, False, tag_criteria, dry_run
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
