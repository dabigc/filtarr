"""Scheduler manager for running batch operations on schedules."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, SupportsFloat, SupportsInt

from filtarr.scheduler.executor import JobExecutor
from filtarr.scheduler.models import (
    RunStatus,
    ScheduleDefinition,
    ScheduleRunRecord,
)
from filtarr.scheduler.triggers import (
    format_trigger_description,
    get_next_run_time,
    parse_trigger,
    trigger_to_apscheduler,
)

if TYPE_CHECKING:
    from apscheduler import AsyncScheduler

    from filtarr.config import Config
    from filtarr.state import StateManager


def _to_int(value: object, default: int = 0) -> int:
    """Safely convert a value to int with a default."""
    if value is None:
        return default
    if isinstance(value, SupportsInt):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _to_float(value: object, default: float = 0.0) -> float:
    """Safely convert a value to float with a default."""
    if value is None:
        return default
    if isinstance(value, SupportsFloat):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages scheduled batch operations using APScheduler."""

    def __init__(
        self,
        config: Config,
        state_manager: StateManager,
    ) -> None:
        """Initialize the scheduler manager.

        Args:
            config: Application configuration
            state_manager: State manager for persisting state
        """
        self._config = config
        self._state = state_manager
        self._scheduler: AsyncScheduler | None = None
        self._running_jobs: set[str] = set()
        self._lock = asyncio.Lock()
        self._executor = JobExecutor(config, state_manager)
        self._started = False

    @property
    def is_running(self) -> bool:
        """Check if the scheduler is running."""
        return self._started and self._scheduler is not None

    async def start(self) -> None:
        """Start the scheduler with configured schedules."""
        if self._started:
            logger.warning("Scheduler already started")
            return

        try:
            from apscheduler import AsyncScheduler
        except ImportError:
            logger.error("APScheduler not installed. Install with: pip install filtarr[scheduler]")
            return

        schedules = self.get_all_schedules()
        enabled_schedules = [s for s in schedules if s.enabled]

        if not enabled_schedules:
            logger.info("No enabled schedules found, scheduler not started")
            return

        logger.info("Starting scheduler with %d enabled schedules", len(enabled_schedules))

        self._scheduler = AsyncScheduler()

        for schedule in enabled_schedules:
            try:
                trigger = trigger_to_apscheduler(schedule.trigger)
                await self._scheduler.add_schedule(
                    self._job_callback,
                    trigger,
                    id=schedule.name,
                    args=[schedule.name],
                )
                next_run = get_next_run_time(schedule.trigger)
                logger.info(
                    "Scheduled %s (%s), next run: %s",
                    schedule.name,
                    format_trigger_description(schedule.trigger),
                    next_run.strftime("%Y-%m-%d %H:%M:%S"),
                )
            except Exception as e:
                logger.error("Failed to add schedule %s: %s", schedule.name, e)

        await self._scheduler.start_in_background()
        self._started = True
        logger.info("Scheduler started successfully")

    async def stop(self, wait: bool = True) -> None:
        """Stop the scheduler gracefully.

        Args:
            wait: Whether to wait for running jobs to complete
        """
        if not self._started or self._scheduler is None:
            return

        logger.info("Stopping scheduler...")

        if wait and self._running_jobs:
            logger.info("Waiting for %d running jobs to complete...", len(self._running_jobs))
            # Wait up to 5 minutes for jobs to complete
            for _ in range(300):
                if not self._running_jobs:
                    break
                await asyncio.sleep(1)

        await self._scheduler.stop()
        self._scheduler = None
        self._started = False
        logger.info("Scheduler stopped")

    def get_all_schedules(self) -> list[ScheduleDefinition]:
        """Get all schedules (config + dynamic).

        Returns:
            Combined list of all schedule definitions
        """
        schedules: list[ScheduleDefinition] = []

        # Load from config file
        for schedule_data in self._config.scheduler.schedules:
            try:
                # Parse trigger from dict
                trigger_data = schedule_data.get("trigger", {})
                if isinstance(trigger_data, dict):
                    trigger = parse_trigger(trigger_data)
                else:
                    continue

                schedule = ScheduleDefinition(
                    name=str(schedule_data.get("name", "")),
                    enabled=bool(schedule_data.get("enabled", True)),
                    target=str(schedule_data.get("target", "both")),  # type: ignore[arg-type]
                    trigger=trigger,
                    batch_size=_to_int(schedule_data.get("batch_size"), 0),
                    delay=_to_float(schedule_data.get("delay"), 0.5),
                    skip_tagged=bool(schedule_data.get("skip_tagged", True)),
                    include_rechecks=bool(schedule_data.get("include_rechecks", True)),
                    no_tag=bool(schedule_data.get("no_tag", False)),
                    dry_run=bool(schedule_data.get("dry_run", False)),
                    strategy=str(schedule_data.get("strategy", "recent")),  # type: ignore[arg-type]
                    seasons=_to_int(schedule_data.get("seasons"), 3),
                    source="config",
                )
                schedules.append(schedule)
            except Exception as e:
                logger.error(
                    "Failed to parse config schedule %s: %s",
                    schedule_data.get("name", "unknown"),
                    e,
                )

        # Load dynamic schedules from state
        for schedule_data in self._state.get_dynamic_schedules():
            try:
                trigger_data = schedule_data.get("trigger", {})
                if isinstance(trigger_data, dict):
                    trigger = parse_trigger(trigger_data)
                else:
                    continue

                schedule = ScheduleDefinition(
                    name=str(schedule_data.get("name", "")),
                    enabled=bool(schedule_data.get("enabled", True)),
                    target=str(schedule_data.get("target", "both")),  # type: ignore[arg-type]
                    trigger=trigger,
                    batch_size=_to_int(schedule_data.get("batch_size"), 0),
                    delay=_to_float(schedule_data.get("delay"), 0.5),
                    skip_tagged=bool(schedule_data.get("skip_tagged", True)),
                    include_rechecks=bool(schedule_data.get("include_rechecks", True)),
                    no_tag=bool(schedule_data.get("no_tag", False)),
                    dry_run=bool(schedule_data.get("dry_run", False)),
                    strategy=str(schedule_data.get("strategy", "recent")),  # type: ignore[arg-type]
                    seasons=_to_int(schedule_data.get("seasons"), 3),
                    source="dynamic",
                )
                schedules.append(schedule)
            except Exception as e:
                logger.error(
                    "Failed to parse dynamic schedule %s: %s",
                    schedule_data.get("name", "unknown"),
                    e,
                )

        return schedules

    def get_schedule(self, name: str) -> ScheduleDefinition | None:
        """Get a schedule by name.

        Args:
            name: Schedule name

        Returns:
            ScheduleDefinition if found, None otherwise
        """
        for schedule in self.get_all_schedules():
            if schedule.name == name.lower():
                return schedule
        return None

    async def run_schedule(self, name: str) -> ScheduleRunRecord:
        """Execute a schedule immediately.

        Args:
            name: Schedule name to run

        Returns:
            ScheduleRunRecord with execution results

        Raises:
            ValueError: If schedule not found
        """
        schedule = self.get_schedule(name)
        if schedule is None:
            raise ValueError(f"Schedule not found: {name}")

        return await self._execute_schedule(schedule)

    def add_schedule(self, schedule: ScheduleDefinition) -> None:
        """Add a dynamic schedule.

        Args:
            schedule: Schedule to add

        Raises:
            ValueError: If schedule with same name exists in config
        """
        # Check if name conflicts with config schedule
        for existing in self._config.scheduler.schedules:
            existing_name = existing.get("name")
            if isinstance(existing_name, str) and existing_name.lower() == schedule.name:
                raise ValueError(
                    f"Cannot add schedule '{schedule.name}': "
                    "a schedule with this name is defined in config.toml"
                )

        # Save to state
        self._state.add_dynamic_schedule(schedule.model_dump(mode="json"))
        logger.info("Added dynamic schedule: %s", schedule.name)

    def remove_schedule(self, name: str) -> bool:
        """Remove a dynamic schedule.

        Args:
            name: Schedule name to remove

        Returns:
            True if removed, False if not found

        Raises:
            ValueError: If schedule is defined in config
        """
        # Check if it's a config schedule
        for existing in self._config.scheduler.schedules:
            existing_name = existing.get("name")
            if isinstance(existing_name, str) and existing_name.lower() == name.lower():
                raise ValueError(
                    f"Cannot remove schedule '{name}': "
                    "it is defined in config.toml (edit config file instead)"
                )

        removed = self._state.remove_dynamic_schedule(name)
        if removed:
            logger.info("Removed dynamic schedule: %s", name)
        return removed

    def enable_schedule(self, name: str) -> bool:
        """Enable a schedule.

        Args:
            name: Schedule name

        Returns:
            True if updated, False if not found
        """
        # Check if it's a config schedule
        for existing in self._config.scheduler.schedules:
            existing_name = existing.get("name")
            if isinstance(existing_name, str) and existing_name.lower() == name.lower():
                raise ValueError(
                    f"Cannot modify schedule '{name}': "
                    "it is defined in config.toml (edit config file instead)"
                )

        return self._state.update_dynamic_schedule(name, {"enabled": True})

    def disable_schedule(self, name: str) -> bool:
        """Disable a schedule.

        Args:
            name: Schedule name

        Returns:
            True if updated, False if not found
        """
        # Check if it's a config schedule
        for existing in self._config.scheduler.schedules:
            existing_name = existing.get("name")
            if isinstance(existing_name, str) and existing_name.lower() == name.lower():
                raise ValueError(
                    f"Cannot modify schedule '{name}': "
                    "it is defined in config.toml (edit config file instead)"
                )

        return self._state.update_dynamic_schedule(name, {"enabled": False})

    def get_running_schedules(self) -> set[str]:
        """Get names of currently running schedules.

        Returns:
            Set of running schedule names
        """
        return self._running_jobs.copy()

    def get_history(
        self,
        schedule_name: str | None = None,
        limit: int | None = None,
    ) -> list[ScheduleRunRecord]:
        """Get schedule run history.

        Args:
            schedule_name: Optional filter by schedule
            limit: Maximum records to return

        Returns:
            List of run records
        """
        records = self._state.get_schedule_history(schedule_name, limit)
        return [
            ScheduleRunRecord(
                schedule_name=str(r.get("schedule_name", "")),
                started_at=datetime.fromisoformat(str(r.get("started_at", ""))),
                completed_at=(
                    datetime.fromisoformat(str(r["completed_at"]))
                    if r.get("completed_at")
                    else None
                ),
                status=RunStatus(str(r.get("status", "failed"))),
                items_processed=_to_int(r.get("items_processed"), 0),
                items_with_4k=_to_int(r.get("items_with_4k"), 0),
                errors=list(e) if isinstance((e := r.get("errors")), list) else [],
            )
            for r in records
        ]

    async def _job_callback(self, schedule_name: str) -> None:
        """APScheduler callback for scheduled jobs.

        Args:
            schedule_name: Name of the schedule to run
        """
        schedule = self.get_schedule(schedule_name)
        if schedule is None:
            logger.error("Schedule not found for callback: %s", schedule_name)
            return

        await self._execute_schedule(schedule)

    async def _execute_schedule(self, schedule: ScheduleDefinition) -> ScheduleRunRecord:
        """Execute a schedule with overlap protection.

        Args:
            schedule: Schedule to execute

        Returns:
            ScheduleRunRecord with results
        """
        async with self._lock:
            if schedule.name in self._running_jobs:
                logger.warning(
                    "Schedule %s is already running, skipping this run",
                    schedule.name,
                )
                # Record skipped run
                now = datetime.now(UTC)
                record = ScheduleRunRecord(
                    schedule_name=schedule.name,
                    started_at=now,
                    completed_at=now,
                    status=RunStatus.SKIPPED,
                )
                self._state.add_schedule_run(record.model_dump(mode="json"))
                return record

            self._running_jobs.add(schedule.name)

        try:
            logger.info("Starting scheduled run: %s", schedule.name)
            result = await self._executor.execute(schedule)
            logger.info(
                "Completed scheduled run: %s (status=%s, items=%d, 4k=%d)",
                schedule.name,
                result.status.value,
                result.items_processed,
                result.items_with_4k,
            )
            return result
        finally:
            async with self._lock:
                self._running_jobs.discard(schedule.name)
