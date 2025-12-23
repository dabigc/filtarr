"""State file management for tracking 4K check history."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import Literal

logger = logging.getLogger(__name__)

STATE_VERSION = 1


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
        if not isinstance(total_items, (int, float)):
            total_items = 0

        return cls(
            batch_id=str(data.get("batch_id", "")),
            item_type=item_type,  # type: ignore[arg-type]
            total_items=int(total_items),
            processed_ids={int(i) for i in processed_ids if isinstance(i, (int, float))},
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
        if not isinstance(tag_applied, (str, type(None))):
            tag_applied = None

        return cls(
            last_checked=last_checked,
            result=result,  # type: ignore[arg-type]
            tag_applied=tag_applied,
        )


@dataclass
class StateFile:
    """State file for tracking check history."""

    version: int = STATE_VERSION
    checks: dict[str, CheckRecord] = field(default_factory=dict)
    batch_progress: BatchProgress | None = None

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

        return cls(version=version, checks=checks, batch_progress=batch_progress)


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
