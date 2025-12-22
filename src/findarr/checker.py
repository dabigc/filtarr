"""Main 4K availability checker combining Radarr and Sonarr."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

from findarr.clients.radarr import RadarrClient
from findarr.clients.sonarr import SonarrClient

if TYPE_CHECKING:
    from findarr.models.common import Release
    from findarr.models.sonarr import Episode


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
class FourKResult:
    """Result of a 4K availability check."""

    item_id: int
    item_type: str  # "movie" or "series"
    has_4k: bool
    releases: list[Release] = field(default_factory=list)
    episodes_checked: list[int] = field(default_factory=list)
    seasons_checked: list[int] = field(default_factory=list)
    strategy_used: SamplingStrategy | None = None

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

    async def check_series(
        self,
        series_id: int,
        *,
        strategy: SamplingStrategy = SamplingStrategy.RECENT,
        seasons_to_check: int = 3,
    ) -> FourKResult:
        """Check if a series has 4K releases available.

        Uses episode-level checking with configurable sampling strategy.
        First checks the latest aired episode for a quick result, then
        samples additional episodes if needed.

        Args:
            series_id: The Sonarr series ID
            strategy: The sampling strategy for selecting episodes
            seasons_to_check: Max seasons to check for RECENT strategy

        Returns:
            FourKResult with availability and checked episode information

        Raises:
            ValueError: If Sonarr is not configured
        """
        if not self._sonarr_config:
            raise ValueError("Sonarr is not configured")

        url, api_key = self._sonarr_config
        async with SonarrClient(url, api_key) as client:
            # Get all episodes for the series
            episodes = await client.get_episodes(series_id)
            today = date.today()

            # Filter to aired episodes
            aired_episodes = [
                e for e in episodes if e.air_date and e.air_date <= today
            ]

            if not aired_episodes:
                # No aired episodes - return empty result
                return FourKResult(
                    item_id=series_id,
                    item_type="series",
                    has_4k=False,
                    strategy_used=strategy,
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
                    return FourKResult(
                        item_id=series_id,
                        item_type="series",
                        has_4k=True,
                        releases=all_releases,
                        episodes_checked=episodes_checked,
                        seasons_checked=seasons_checked,
                        strategy_used=strategy,
                    )

            # No 4K found after checking all sampled episodes
            return FourKResult(
                item_id=series_id,
                item_type="series",
                has_4k=False,
                releases=all_releases,
                episodes_checked=episodes_checked,
                seasons_checked=seasons_checked,
                strategy_used=strategy,
            )
