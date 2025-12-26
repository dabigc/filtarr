"""Data models for the scheduler module."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - needed for Pydantic at runtime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TriggerType(str, Enum):
    """Type of schedule trigger."""

    INTERVAL = "interval"
    CRON = "cron"


class IntervalTrigger(BaseModel):
    """Interval-based trigger configuration."""

    type: Literal[TriggerType.INTERVAL] = TriggerType.INTERVAL
    weeks: int = Field(default=0, ge=0)
    days: int = Field(default=0, ge=0)
    hours: int = Field(default=0, ge=0)
    minutes: int = Field(default=0, ge=0)
    seconds: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def at_least_one_nonzero(self) -> IntervalTrigger:
        """Ensure at least one interval component is set."""
        if all(v == 0 for v in [self.weeks, self.days, self.hours, self.minutes, self.seconds]):
            raise ValueError("At least one interval component must be non-zero")
        return self

    def total_seconds(self) -> int:
        """Calculate total interval in seconds."""
        return (
            self.weeks * 7 * 24 * 3600
            + self.days * 24 * 3600
            + self.hours * 3600
            + self.minutes * 60
            + self.seconds
        )


class CronTrigger(BaseModel):
    """Cron expression-based trigger configuration."""

    type: Literal[TriggerType.CRON] = TriggerType.CRON
    expression: str = Field(..., min_length=9)  # Minimum: "* * * * *"

    @field_validator("expression")
    @classmethod
    def validate_cron_expression(cls, v: str) -> str:
        """Validate cron expression syntax."""
        try:
            from croniter import croniter

            if not croniter.is_valid(v):
                raise ValueError(f"Invalid cron expression: {v}")
        except ImportError:
            # If croniter not installed, do basic validation
            parts = v.split()
            if len(parts) != 5:
                raise ValueError(
                    f"Invalid cron expression: expected 5 fields, got {len(parts)}"
                ) from None
        return v


# Union type for triggers
Trigger = Annotated[IntervalTrigger | CronTrigger, Field(discriminator="type")]


class ScheduleTarget(str, Enum):
    """Target type for scheduled batch operations."""

    MOVIES = "movies"
    SERIES = "series"
    BOTH = "both"


class SeriesStrategy(str, Enum):
    """Strategy for checking series episodes."""

    RECENT = "recent"
    DISTRIBUTED = "distributed"
    ALL = "all"


class ScheduleDefinition(BaseModel):
    """Definition of a scheduled batch operation."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Unique schedule identifier",
    )
    enabled: bool = Field(default=True, description="Whether the schedule is active")
    target: ScheduleTarget = Field(..., description="What to check: movies, series, or both")
    trigger: Trigger = Field(..., description="When to run: interval or cron")

    # Batch operation parameters
    batch_size: int = Field(default=0, ge=0, description="Max items per run (0=unlimited)")
    delay: float = Field(default=0.5, ge=0, description="Delay between checks in seconds")
    concurrency: int = Field(
        default=1, ge=1, le=50, description="Max concurrent checks (1=sequential)"
    )
    skip_tagged: bool = Field(default=True, description="Skip items with existing 4K tags")
    include_rechecks: bool = Field(default=True, description="Include stale unavailable items")
    no_tag: bool = Field(default=False, description="Disable automatic tagging")
    dry_run: bool = Field(default=False, description="Preview mode - don't apply tags")

    # Series-specific parameters
    strategy: SeriesStrategy = Field(
        default=SeriesStrategy.RECENT, description="Series checking strategy"
    )
    seasons: int = Field(default=3, ge=1, description="Number of seasons to check for series")

    # Metadata
    source: Literal["config", "dynamic"] = Field(
        default="dynamic", description="Where this schedule was defined"
    )

    def model_post_init(self, __context: object) -> None:
        """Normalize the name to lowercase."""
        object.__setattr__(self, "name", self.name.lower())


class RunStatus(str, Enum):
    """Status of a scheduled run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScheduleRunRecord(BaseModel):
    """Record of a scheduled run execution."""

    schedule_name: str = Field(..., description="Name of the schedule that ran")
    started_at: datetime = Field(..., description="When the run started")
    completed_at: datetime | None = Field(default=None, description="When the run completed")
    status: RunStatus = Field(..., description="Final status of the run")
    items_processed: int = Field(default=0, ge=0, description="Total items checked")
    items_with_4k: int = Field(default=0, ge=0, description="Items with 4K available")
    errors: list[str] = Field(default_factory=list, description="Error messages")

    def duration_seconds(self) -> float | None:
        """Calculate run duration in seconds."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


class SchedulerState(BaseModel):
    """Scheduler-specific state stored in the state file."""

    dynamic_schedules: list[ScheduleDefinition] = Field(
        default_factory=list, description="Dynamically added schedules"
    )
    schedule_history: list[ScheduleRunRecord] = Field(
        default_factory=list, description="History of scheduled runs"
    )

    def add_schedule(self, schedule: ScheduleDefinition) -> None:
        """Add a dynamic schedule."""
        # Remove existing schedule with same name if present
        self.dynamic_schedules = [s for s in self.dynamic_schedules if s.name != schedule.name]
        self.dynamic_schedules.append(schedule)

    def remove_schedule(self, name: str) -> bool:
        """Remove a dynamic schedule by name. Returns True if removed."""
        original_len = len(self.dynamic_schedules)
        self.dynamic_schedules = [s for s in self.dynamic_schedules if s.name != name.lower()]
        return len(self.dynamic_schedules) < original_len

    def get_schedule(self, name: str) -> ScheduleDefinition | None:
        """Get a dynamic schedule by name."""
        for schedule in self.dynamic_schedules:
            if schedule.name == name.lower():
                return schedule
        return None

    def add_run_record(self, record: ScheduleRunRecord) -> None:
        """Add a run record to history."""
        self.schedule_history.append(record)

    def prune_history(self, limit: int) -> int:
        """Prune history to keep only the most recent entries. Returns count removed."""
        if len(self.schedule_history) <= limit:
            return 0
        removed = len(self.schedule_history) - limit
        self.schedule_history = self.schedule_history[-limit:]
        return removed

    def get_history(
        self, schedule_name: str | None = None, limit: int | None = None
    ) -> list[ScheduleRunRecord]:
        """Get run history, optionally filtered by schedule name."""
        history = self.schedule_history
        if schedule_name:
            history = [r for r in history if r.schedule_name == schedule_name.lower()]
        # Return most recent first
        history = list(reversed(history))
        if limit:
            history = history[:limit]
        return history
