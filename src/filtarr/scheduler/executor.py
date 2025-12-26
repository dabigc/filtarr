"""Job executor for scheduled batch operations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from filtarr.checker import ReleaseChecker, SamplingStrategy, SearchResult
from filtarr.clients.radarr import RadarrClient
from filtarr.clients.sonarr import SonarrClient
from filtarr.scheduler.models import (
    RunStatus,
    ScheduleDefinition,
    ScheduleRunRecord,
    ScheduleTarget,
    SeriesStrategy,
)

if TYPE_CHECKING:
    from filtarr.config import Config
    from filtarr.models.radarr import Movie
    from filtarr.models.sonarr import Series
    from filtarr.state import StateManager

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result from processing a batch of items."""

    items_processed: int = 0
    items_with_4k: int = 0
    errors: list[str] = field(default_factory=list)


class JobExecutor:
    """Executes batch operations for scheduled runs."""

    def __init__(
        self,
        config: Config,
        state_manager: StateManager,
    ) -> None:
        """Initialize the job executor.

        Args:
            config: Application configuration
            state_manager: State manager for recording results
        """
        self._config = config
        self._state = state_manager

    async def execute(
        self,
        schedule: ScheduleDefinition,
    ) -> ScheduleRunRecord:
        """Execute a batch operation based on schedule definition.

        Args:
            schedule: The schedule definition to execute

        Returns:
            ScheduleRunRecord with execution results
        """
        started_at = datetime.now(UTC)
        record = ScheduleRunRecord(
            schedule_name=schedule.name,
            started_at=started_at,
            status=RunStatus.RUNNING,
        )

        # Record the start
        self._state.add_schedule_run(record.model_dump(mode="json"))

        items_processed = 0
        items_with_4k = 0
        errors: list[str] = []

        try:
            # Get items to check based on target
            movies_to_check: list[Movie] = []
            series_to_check: list[Series] = []

            if schedule.target in (ScheduleTarget.MOVIES, ScheduleTarget.BOTH):
                movies_to_check = await self._get_movies_to_check(schedule)

            if schedule.target in (ScheduleTarget.SERIES, ScheduleTarget.BOTH):
                series_to_check = await self._get_series_to_check(schedule)

            total_items = len(movies_to_check) + len(series_to_check)
            logger.info(
                "Schedule %s: checking %d movies and %d series (concurrency=%d)",
                schedule.name,
                len(movies_to_check),
                len(series_to_check),
                schedule.concurrency,
            )

            # Calculate remaining batch capacity
            remaining_batch = schedule.batch_size if schedule.batch_size > 0 else float("inf")

            # Apply batch size limit to movies
            movies_batch = movies_to_check[: int(min(len(movies_to_check), remaining_batch))]
            if len(movies_batch) < len(movies_to_check):
                logger.info(
                    "Schedule %s: limiting movies to %d due to batch size",
                    schedule.name,
                    len(movies_batch),
                )

            # Process movies concurrently
            movie_result = await self._process_movies_batch(movies_batch, schedule)
            items_processed += movie_result.items_processed
            items_with_4k += movie_result.items_with_4k
            errors.extend(movie_result.errors)

            # Update remaining batch capacity
            remaining_batch -= movie_result.items_processed

            # Apply batch size limit to series
            series_batch = series_to_check[: int(min(len(series_to_check), remaining_batch))]
            if remaining_batch <= 0:
                logger.info(
                    "Schedule %s: batch size limit (%d) reached after movies",
                    schedule.name,
                    schedule.batch_size,
                )
            elif len(series_batch) < len(series_to_check):
                logger.info(
                    "Schedule %s: limiting series to %d due to batch size",
                    schedule.name,
                    len(series_batch),
                )

            # Process series concurrently
            if series_batch:
                series_result = await self._process_series_batch(series_batch, schedule)
                items_processed += series_result.items_processed
                items_with_4k += series_result.items_with_4k
                errors.extend(series_result.errors)

            # Determine final status
            status = RunStatus.COMPLETED
            if items_processed == 0 and total_items > 0:
                # We had items but processed none - likely all errors
                status = RunStatus.FAILED

            logger.info(
                "Schedule %s completed: %d/%d items, %d with 4K, %d errors",
                schedule.name,
                items_processed,
                total_items,
                items_with_4k,
                len(errors),
            )

        except Exception as e:
            error_msg = f"Schedule execution failed: {e}"
            logger.exception(error_msg)
            errors.append(error_msg)
            status = RunStatus.FAILED

        # Update the run record
        completed_at = datetime.now(UTC)
        self._state.update_schedule_run(
            schedule.name,
            started_at.isoformat(),
            {
                "completed_at": completed_at.isoformat(),
                "status": status.value,
                "items_processed": items_processed,
                "items_with_4k": items_with_4k,
                "errors": errors,
            },
        )

        # Prune history if needed
        self._state.prune_schedule_history(self._config.scheduler.history_limit)

        return ScheduleRunRecord(
            schedule_name=schedule.name,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            items_processed=items_processed,
            items_with_4k=items_with_4k,
            errors=errors,
        )

    async def _process_movies_batch(
        self, movies: list[Movie], schedule: ScheduleDefinition
    ) -> BatchResult:
        """Process a batch of movies with concurrent execution.

        Uses a single ReleaseChecker instance for the entire batch to enable
        connection pooling across all movie checks.

        Args:
            movies: List of movies to check
            schedule: Schedule definition

        Returns:
            BatchResult with aggregated results
        """
        if not movies:
            return BatchResult()

        semaphore = asyncio.Semaphore(schedule.concurrency)
        result = BatchResult()
        lock = asyncio.Lock()

        # Create a single checker for the entire batch (connection pooling)
        checker = self._create_checker(need_radarr=True)

        async def check_with_limit(movie: Movie) -> None:
            async with semaphore:
                try:
                    search_result = await self._check_movie(movie.id, schedule, checker)
                    async with lock:
                        result.items_processed += 1
                        if search_result and search_result.has_match:
                            result.items_with_4k += 1

                        # Record in state
                        if search_result and not schedule.dry_run and not schedule.no_tag:
                            tag_applied = (
                                search_result.tag_result.tag_applied
                                if search_result.tag_result
                                else None
                            )
                            self._state.record_check(
                                "movie", movie.id, search_result.has_match, tag_applied
                            )

                except Exception as e:
                    error_msg = f"Error checking movie {movie.id} ({movie.title}): {e}"
                    logger.error(error_msg)
                    async with lock:
                        result.errors.append(error_msg)

            # Apply delay after releasing semaphore to avoid blocking concurrent workers
            if schedule.delay > 0:
                await asyncio.sleep(schedule.delay)

        async with checker:
            await asyncio.gather(*[check_with_limit(movie) for movie in movies])
        return result

    async def _process_series_batch(
        self, series_list: list[Series], schedule: ScheduleDefinition
    ) -> BatchResult:
        """Process a batch of series with concurrent execution.

        Uses a single ReleaseChecker instance for the entire batch to enable
        connection pooling across all series checks.

        Args:
            series_list: List of series to check
            schedule: Schedule definition

        Returns:
            BatchResult with aggregated results
        """
        if not series_list:
            return BatchResult()

        semaphore = asyncio.Semaphore(schedule.concurrency)
        result = BatchResult()
        lock = asyncio.Lock()

        # Create a single checker for the entire batch (connection pooling)
        checker = self._create_checker(need_sonarr=True)

        async def check_with_limit(series: Series) -> None:
            async with semaphore:
                try:
                    search_result = await self._check_series(series.id, schedule, checker)
                    async with lock:
                        result.items_processed += 1
                        if search_result and search_result.has_match:
                            result.items_with_4k += 1

                        # Record in state
                        if search_result and not schedule.dry_run and not schedule.no_tag:
                            tag_applied = (
                                search_result.tag_result.tag_applied
                                if search_result.tag_result
                                else None
                            )
                            self._state.record_check(
                                "series", series.id, search_result.has_match, tag_applied
                            )

                except Exception as e:
                    error_msg = f"Error checking series {series.id} ({series.title}): {e}"
                    logger.error(error_msg)
                    async with lock:
                        result.errors.append(error_msg)

            # Apply delay after releasing semaphore to avoid blocking concurrent workers
            if schedule.delay > 0:
                await asyncio.sleep(schedule.delay)

        async with checker:
            await asyncio.gather(*[check_with_limit(series) for series in series_list])
        return result

    async def _get_movies_to_check(self, schedule: ScheduleDefinition) -> list[Movie]:
        """Get list of movies to check based on schedule settings.

        Args:
            schedule: Schedule definition

        Returns:
            List of movies to check
        """
        radarr = self._config.require_radarr()
        async with RadarrClient(radarr.url, radarr.api_key, timeout=self._config.timeout) as client:
            all_movies = await client.get_all_movies()

            if not schedule.skip_tagged:
                return all_movies

            # Get tags to skip using the new pattern-based API
            available_tag, unavailable_tag = self._config.tags.get_tag_names("4k")
            tag_names = {available_tag, unavailable_tag}
            all_tags = await client.get_tags()
            skip_tag_ids = {tag.id for tag in all_tags if tag.label in tag_names}

            # Filter out already-tagged movies
            return [
                movie
                for movie in all_movies
                if not any(tag_id in skip_tag_ids for tag_id in movie.tags)
            ]

    async def _get_series_to_check(self, schedule: ScheduleDefinition) -> list[Series]:
        """Get list of series to check based on schedule settings.

        Args:
            schedule: Schedule definition

        Returns:
            List of series to check
        """
        sonarr = self._config.require_sonarr()
        async with SonarrClient(sonarr.url, sonarr.api_key, timeout=self._config.timeout) as client:
            all_series = await client.get_all_series()

            if not schedule.skip_tagged:
                return all_series

            # Get tags to skip using the new pattern-based API
            available_tag, unavailable_tag = self._config.tags.get_tag_names("4k")
            tag_names = {available_tag, unavailable_tag}
            all_tags = await client.get_tags()
            skip_tag_ids = {tag.id for tag in all_tags if tag.label in tag_names}

            # Filter out already-tagged series
            return [
                series
                for series in all_series
                if not any(tag_id in skip_tag_ids for tag_id in series.tags)
            ]

    async def _check_movie(
        self,
        movie_id: int,
        schedule: ScheduleDefinition,
        checker: ReleaseChecker | None = None,
    ) -> SearchResult | None:
        """Check a single movie for 4K availability.

        Args:
            movie_id: Movie ID to check
            schedule: Schedule definition
            checker: Optional pre-created ReleaseChecker for connection pooling.
                     If not provided, creates a new checker (backward compatibility).

        Returns:
            SearchResult if successful, None otherwise
        """
        if checker is None:
            # Backward compatibility: create a new checker if none provided
            checker = self._create_checker(need_radarr=True)
        return await checker.check_movie(
            movie_id,
            apply_tags=not schedule.no_tag,
            dry_run=schedule.dry_run,
        )

    async def _check_series(
        self,
        series_id: int,
        schedule: ScheduleDefinition,
        checker: ReleaseChecker | None = None,
    ) -> SearchResult | None:
        """Check a single series for 4K availability.

        Args:
            series_id: Series ID to check
            schedule: Schedule definition
            checker: Optional pre-created ReleaseChecker for connection pooling.
                     If not provided, creates a new checker (backward compatibility).

        Returns:
            SearchResult if successful, None otherwise
        """
        # Map schedule strategy to SamplingStrategy
        strategy_map = {
            SeriesStrategy.RECENT: SamplingStrategy.RECENT,
            SeriesStrategy.DISTRIBUTED: SamplingStrategy.DISTRIBUTED,
            SeriesStrategy.ALL: SamplingStrategy.ALL,
        }
        sampling_strategy = strategy_map[schedule.strategy]

        if checker is None:
            # Backward compatibility: create a new checker if none provided
            checker = self._create_checker(need_sonarr=True)
        return await checker.check_series(
            series_id,
            strategy=sampling_strategy,
            seasons_to_check=schedule.seasons,
            apply_tags=not schedule.no_tag,
            dry_run=schedule.dry_run,
        )

    def _create_checker(
        self, need_radarr: bool = False, need_sonarr: bool = False
    ) -> ReleaseChecker:
        """Create a ReleaseChecker instance.

        Args:
            need_radarr: Whether Radarr is needed
            need_sonarr: Whether Sonarr is needed

        Returns:
            Configured ReleaseChecker instance
        """
        radarr_url = None
        radarr_api_key = None
        sonarr_url = None
        sonarr_api_key = None

        if need_radarr and self._config.radarr:
            radarr_url = self._config.radarr.url
            radarr_api_key = self._config.radarr.api_key

        if need_sonarr and self._config.sonarr:
            sonarr_url = self._config.sonarr.url
            sonarr_api_key = self._config.sonarr.api_key

        return ReleaseChecker(
            radarr_url=radarr_url,
            radarr_api_key=radarr_api_key,
            sonarr_url=sonarr_url,
            sonarr_api_key=sonarr_api_key,
            timeout=self._config.timeout,
            tag_config=self._config.tags,
        )


async def execute_schedule(
    config: Config,
    state_manager: StateManager,
    schedule: ScheduleDefinition,
) -> ScheduleRunRecord:
    """Convenience function to execute a schedule.

    Args:
        config: Application configuration
        state_manager: State manager
        schedule: Schedule to execute

    Returns:
        ScheduleRunRecord with execution results
    """
    executor = JobExecutor(config, state_manager)
    return await executor.execute(schedule)
