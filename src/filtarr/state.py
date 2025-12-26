"""State file management for tracking release check history."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import Literal

logger = logging.getLogger(__name__)

STATE_VERSION = 2


@dataclass
class BatchProgress:
    """Track progress of a batch operation for resume capability."""

    batch_id: str  # Unique ID for this batch run
    item_type: Literal["movie", "series", "mixed"]
    total_items: int
    processed_ids: set[int] = field(default_factory=set)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def processed_count(self) -> int:
        """Number of items processed."""
        return len(self.processed_ids)

    @property
    def remaining_count(self) -> int:
        """Number of items remaining."""
        return self.total_items - self.processed_count

    def mark_processed(self, item_id: int) -> None:
        """Mark an item as processed."""
        self.processed_ids.add(item_id)

    def is_processed(self, item_id: int) -> bool:
        """Check if an item has been processed."""
        return item_id in self.processed_ids

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "batch_id": self.batch_id,
            "item_type": self.item_type,
            "total_items": self.total_items,
            "processed_ids": list(self.processed_ids),
            "started_at": self.started_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BatchProgress:
        """Create from dictionary."""
        started_at_str = data.get("started_at", "")
        if isinstance(started_at_str, str) and started_at_str:
            started_at = datetime.fromisoformat(started_at_str)
        else:
            started_at = datetime.now(UTC)

        processed_ids = data.get("processed_ids", [])
        if not isinstance(processed_ids, list):
            processed_ids = []

        item_type = data.get("item_type", "mixed")
        if item_type not in ("movie", "series", "mixed"):
            item_type = "mixed"

        total_items = data.get("total_items", 0)
        if not isinstance(total_items, int | float):
            total_items = 0

        return cls(
            batch_id=str(data.get("batch_id", "")),
            item_type=item_type,  # type: ignore[arg-type]
            total_items=int(total_items),
            processed_ids={int(i) for i in processed_ids if isinstance(i, int | float)},
            started_at=started_at,
        )


@dataclass
class CheckRecord:
    """Record of a single 4K availability check."""

    last_checked: datetime
    result: Literal["available", "unavailable"]
    tag_applied: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_checked": self.last_checked.isoformat(),
            "result": self.result,
            "tag_applied": self.tag_applied,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CheckRecord:
        """Create from dictionary."""
        last_checked_str = data.get("last_checked", "")
        if isinstance(last_checked_str, str) and last_checked_str:
            last_checked = datetime.fromisoformat(last_checked_str)
        else:
            last_checked = datetime.now(UTC)

        result = data.get("result", "unavailable")
        if result not in ("available", "unavailable"):
            result = "unavailable"

        tag_applied = data.get("tag_applied")
        if not isinstance(tag_applied, str | None):
            tag_applied = None

        return cls(
            last_checked=last_checked,
            result=result,  # type: ignore[arg-type]
            tag_applied=tag_applied,
        )


@dataclass
class StateFile:
    """State file for tracking check history and scheduler state."""

    version: int = STATE_VERSION
    checks: dict[str, CheckRecord] = field(default_factory=dict)
    batch_progress: BatchProgress | None = None
    # Scheduler state (stored as dicts, converted to/from models by StateManager)
    dynamic_schedules: list[dict[str, object]] = field(default_factory=list)
    schedule_history: list[dict[str, object]] = field(default_factory=list)

    @staticmethod
    def _make_key(item_type: Literal["movie", "series"], item_id: int) -> str:
        """Create a key for the checks dictionary."""
        return f"{item_type}:{item_id}"

    def get_check(self, item_type: Literal["movie", "series"], item_id: int) -> CheckRecord | None:
        """Get the check record for an item.

        Args:
            item_type: "movie" or "series"
            item_id: The item ID

        Returns:
            CheckRecord if found, None otherwise
        """
        key = self._make_key(item_type, item_id)
        return self.checks.get(key)

    def record_check(
        self,
        item_type: Literal["movie", "series"],
        item_id: int,
        has_4k: bool,
        tag_applied: str | None = None,
    ) -> None:
        """Record a check result.

        Args:
            item_type: "movie" or "series"
            item_id: The item ID
            has_4k: Whether 4K was available
            tag_applied: The tag that was applied (if any)
        """
        key = self._make_key(item_type, item_id)
        self.checks[key] = CheckRecord(
            last_checked=datetime.now(UTC),
            result="available" if has_4k else "unavailable",
            tag_applied=tag_applied,
        )

    def get_stale_unavailable_items(
        self, recheck_days: int
    ) -> list[tuple[Literal["movie", "series"], int]]:
        """Get items marked unavailable that haven't been checked recently.

        Args:
            recheck_days: Number of days after which to recheck

        Returns:
            List of (item_type, item_id) tuples for stale items
        """
        cutoff = datetime.now(UTC) - timedelta(days=recheck_days)
        stale_items: list[tuple[Literal["movie", "series"], int]] = []

        for key, record in self.checks.items():
            if record.result == "unavailable" and record.last_checked < cutoff:
                parts = key.split(":", 1)
                if len(parts) == 2:
                    item_type = parts[0]
                    if item_type in ("movie", "series"):
                        item_id = int(parts[1])
                        stale_items.append((item_type, item_id))  # type: ignore[arg-type]

        return stale_items

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, object] = {
            "version": self.version,
            "checks": {key: record.to_dict() for key, record in self.checks.items()},
        }
        if self.batch_progress is not None:
            result["batch_progress"] = self.batch_progress.to_dict()
        if self.dynamic_schedules:
            result["dynamic_schedules"] = self.dynamic_schedules
        if self.schedule_history:
            result["schedule_history"] = self.schedule_history
        return result

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> StateFile:
        """Create from dictionary."""
        version = data.get("version", STATE_VERSION)
        if not isinstance(version, int):
            version = STATE_VERSION

        checks_data = data.get("checks", {})
        if not isinstance(checks_data, dict):
            checks_data = {}

        checks: dict[str, CheckRecord] = {}
        for key, record_data in checks_data.items():
            if isinstance(record_data, dict):
                checks[key] = CheckRecord.from_dict(record_data)

        batch_progress: BatchProgress | None = None
        batch_data = data.get("batch_progress")
        if isinstance(batch_data, dict):
            batch_progress = BatchProgress.from_dict(batch_data)

        # Load scheduler state
        dynamic_schedules = data.get("dynamic_schedules", [])
        if not isinstance(dynamic_schedules, list):
            dynamic_schedules = []
        # Filter to only dicts
        dynamic_schedules = [s for s in dynamic_schedules if isinstance(s, dict)]

        schedule_history = data.get("schedule_history", [])
        if not isinstance(schedule_history, list):
            schedule_history = []
        # Filter to only dicts
        schedule_history = [r for r in schedule_history if isinstance(r, dict)]

        return cls(
            version=version,
            checks=checks,
            batch_progress=batch_progress,
            dynamic_schedules=dynamic_schedules,
            schedule_history=schedule_history,
        )


class StateManager:
    """Manager for loading and saving state files."""

    def __init__(self, path: Path) -> None:
        """Initialize the state manager.

        Args:
            path: Path to the state file
        """
        self.path = path
        self._state: StateFile | None = None

    def load(self) -> StateFile:
        """Load state from file, creating empty state if file doesn't exist.

        Returns:
            The loaded or empty StateFile
        """
        if self._state is not None:
            return self._state

        if not self.path.exists():
            self._state = StateFile()
            return self._state

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._state = StateFile.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load state file %s: %s", self.path, e)
            self._state = StateFile()

        return self._state

    def save(self) -> None:
        """Save state to file."""
        if self._state is None:
            return

        # Ensure directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(self._state.to_dict(), f, indent=2)
        except OSError as e:
            logger.error("Failed to save state file %s: %s", self.path, e)

    def record_check(
        self,
        item_type: Literal["movie", "series"],
        item_id: int,
        has_4k: bool,
        tag_applied: str | None = None,
    ) -> None:
        """Record a check result and save state.

        Args:
            item_type: "movie" or "series"
            item_id: The item ID
            has_4k: Whether 4K was available
            tag_applied: The tag that was applied (if any)
        """
        state = self.load()
        state.record_check(item_type, item_id, has_4k, tag_applied)
        self.save()

    def get_stale_unavailable_items(
        self, recheck_days: int
    ) -> list[tuple[Literal["movie", "series"], int]]:
        """Get items marked unavailable that need rechecking.

        Args:
            recheck_days: Number of days after which to recheck

        Returns:
            List of (item_type, item_id) tuples for stale items
        """
        state = self.load()
        return state.get_stale_unavailable_items(recheck_days)

    def get_check(self, item_type: Literal["movie", "series"], item_id: int) -> CheckRecord | None:
        """Get the check record for an item.

        Args:
            item_type: "movie" or "series"
            item_id: The item ID

        Returns:
            CheckRecord if found, None otherwise
        """
        state = self.load()
        return state.get_check(item_type, item_id)

    def is_recently_checked(
        self, item_type: Literal["movie", "series"], item_id: int, ttl_hours: int
    ) -> bool:
        """Check if an item was checked within the TTL period.

        Args:
            item_type: "movie" or "series"
            item_id: The item ID
            ttl_hours: TTL in hours (0 means TTL is disabled, always returns False)

        Returns:
            True if item was checked within TTL, False otherwise
        """
        if ttl_hours <= 0:
            return False

        record = self.get_check(item_type, item_id)
        if record is None:
            return False

        # Calculate elapsed time since last check
        now = datetime.now(UTC)
        # Handle timezone-naive datetimes (backwards compatibility)
        last_checked = record.last_checked
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=UTC)

        elapsed = now - last_checked
        return elapsed.total_seconds() <= (ttl_hours * 3600)

    def get_cached_result(
        self, item_type: Literal["movie", "series"], item_id: int, ttl_hours: int
    ) -> CheckRecord | None:
        """Get cached result if within TTL period.

        Args:
            item_type: "movie" or "series"
            item_id: The item ID
            ttl_hours: TTL in hours (0 means TTL is disabled, always returns None)

        Returns:
            CheckRecord if within TTL, None otherwise
        """
        if not self.is_recently_checked(item_type, item_id, ttl_hours):
            return None
        return self.get_check(item_type, item_id)

    def ensure_initialized(self) -> None:
        """Ensure the state file exists, creating it if necessary.

        This method loads the state (creating an empty one if needed)
        and saves it to ensure the state file exists on disk.
        """
        self.load()
        self.save()

    def start_batch(
        self,
        batch_id: str,
        item_type: Literal["movie", "series", "mixed"],
        total_items: int,
    ) -> BatchProgress:
        """Start a new batch operation.

        Args:
            batch_id: Unique identifier for this batch
            item_type: Type of items being processed
            total_items: Total number of items to process

        Returns:
            The new BatchProgress object
        """
        state = self.load()
        state.batch_progress = BatchProgress(
            batch_id=batch_id,
            item_type=item_type,
            total_items=total_items,
        )
        self.save()
        return state.batch_progress

    def get_batch_progress(self) -> BatchProgress | None:
        """Get the current batch progress if any.

        Returns:
            BatchProgress if a batch is in progress, None otherwise
        """
        state = self.load()
        return state.batch_progress

    def update_batch_progress(self, item_id: int) -> None:
        """Mark an item as processed in the current batch.

        Args:
            item_id: The ID of the processed item
        """
        state = self.load()
        if state.batch_progress is not None:
            state.batch_progress.mark_processed(item_id)
            self.save()

    def clear_batch_progress(self) -> None:
        """Clear the batch progress (call on successful completion)."""
        state = self.load()
        state.batch_progress = None
        self.save()

    # Scheduler state management

    def get_dynamic_schedules(self) -> list[dict[str, object]]:
        """Get all dynamic schedules.

        Returns:
            List of schedule dictionaries
        """
        state = self.load()
        return state.dynamic_schedules

    def add_dynamic_schedule(self, schedule: dict[str, object]) -> None:
        """Add or update a dynamic schedule.

        Args:
            schedule: Schedule dictionary (must have 'name' key)
        """
        state = self.load()
        name_val = schedule.get("name")
        name = name_val.lower() if isinstance(name_val, str) else ""
        if not name:
            raise ValueError("Schedule must have a 'name' field")

        # Remove existing schedule with same name
        state.dynamic_schedules = [
            s
            for s in state.dynamic_schedules
            if not (isinstance((n := s.get("name")), str) and n.lower() == name)
        ]
        state.dynamic_schedules.append(schedule)
        self.save()

    def remove_dynamic_schedule(self, name: str) -> bool:
        """Remove a dynamic schedule by name.

        Args:
            name: Schedule name to remove

        Returns:
            True if schedule was removed, False if not found
        """
        state = self.load()
        original_len = len(state.dynamic_schedules)
        state.dynamic_schedules = [
            s
            for s in state.dynamic_schedules
            if not (isinstance((n := s.get("name")), str) and n.lower() == name.lower())
        ]
        if len(state.dynamic_schedules) < original_len:
            self.save()
            return True
        return False

    def get_dynamic_schedule(self, name: str) -> dict[str, object] | None:
        """Get a dynamic schedule by name.

        Args:
            name: Schedule name

        Returns:
            Schedule dictionary if found, None otherwise
        """
        state = self.load()
        for schedule in state.dynamic_schedules:
            sched_name = schedule.get("name")
            if isinstance(sched_name, str) and sched_name.lower() == name.lower():
                return schedule
        return None

    def update_dynamic_schedule(self, name: str, updates: dict[str, object]) -> bool:
        """Update a dynamic schedule.

        Args:
            name: Schedule name to update
            updates: Dictionary of fields to update

        Returns:
            True if schedule was updated, False if not found
        """
        state = self.load()
        for i, schedule in enumerate(state.dynamic_schedules):
            sched_name = schedule.get("name")
            if isinstance(sched_name, str) and sched_name.lower() == name.lower():
                state.dynamic_schedules[i] = {**schedule, **updates}
                self.save()
                return True
        return False

    def get_schedule_history(
        self,
        schedule_name: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """Get schedule run history.

        Args:
            schedule_name: Optional filter by schedule name
            limit: Maximum number of records to return

        Returns:
            List of run record dictionaries (most recent first)
        """
        state = self.load()
        history = state.schedule_history

        if schedule_name:
            history = [
                r
                for r in history
                if isinstance((n := r.get("schedule_name")), str)
                and n.lower() == schedule_name.lower()
            ]

        # Return most recent first
        history = list(reversed(history))

        if limit:
            history = history[:limit]

        return history

    def add_schedule_run(self, record: dict[str, object]) -> None:
        """Add a schedule run record.

        Args:
            record: Run record dictionary
        """
        state = self.load()
        state.schedule_history.append(record)
        self.save()

    def update_schedule_run(
        self,
        schedule_name: str,
        started_at: str,
        updates: dict[str, object],
    ) -> bool:
        """Update an existing run record (e.g., to mark as completed).

        Args:
            schedule_name: Schedule name
            started_at: ISO timestamp of the run start
            updates: Dictionary of fields to update

        Returns:
            True if record was updated, False if not found
        """
        state = self.load()
        for i, record in enumerate(state.schedule_history):
            rec_name = record.get("schedule_name")
            if (
                isinstance(rec_name, str)
                and rec_name.lower() == schedule_name.lower()
                and record.get("started_at") == started_at
            ):
                state.schedule_history[i] = {**record, **updates}
                self.save()
                return True
        return False

    def prune_schedule_history(self, limit: int) -> int:
        """Prune schedule history to keep only the most recent entries.

        Args:
            limit: Maximum number of entries to keep

        Returns:
            Number of entries removed
        """
        state = self.load()
        if len(state.schedule_history) <= limit:
            return 0

        removed = len(state.schedule_history) - limit
        state.schedule_history = state.schedule_history[-limit:]
        self.save()
        return removed
