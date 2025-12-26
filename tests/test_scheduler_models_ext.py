"""Extended tests for scheduler models - SchedulerState and CronTrigger edge cases."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from filtarr.scheduler.models import (
    CronTrigger,
    IntervalTrigger,
    RunStatus,
    ScheduleDefinition,
    SchedulerState,
    ScheduleRunRecord,
    ScheduleTarget,
)


class TestSchedulerStateAddSchedule:
    """Tests for SchedulerState.add_schedule() method."""

    def test_add_schedule_new(self) -> None:
        """Test adding a new schedule."""
        state = SchedulerState()
        schedule = ScheduleDefinition(
            name="new-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )

        state.add_schedule(schedule)

        assert len(state.dynamic_schedules) == 1
        assert state.dynamic_schedules[0].name == "new-schedule"

    def test_add_schedule_replaces_existing(self) -> None:
        """Test that adding a schedule with the same name replaces the existing one."""
        state = SchedulerState()

        # Add first schedule
        schedule1 = ScheduleDefinition(
            name="test-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        state.add_schedule(schedule1)

        # Add schedule with same name but different target
        schedule2 = ScheduleDefinition(
            name="test-schedule",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=12),
        )
        state.add_schedule(schedule2)

        # Should still have only one schedule
        assert len(state.dynamic_schedules) == 1
        # Should be the new one
        assert state.dynamic_schedules[0].target == ScheduleTarget.SERIES
        assert state.dynamic_schedules[0].trigger.hours == 12

    def test_add_schedule_case_insensitive_replace(self) -> None:
        """Test that schedule name matching is case-insensitive for replacement."""
        state = SchedulerState()

        # Add schedule with lowercase name
        schedule1 = ScheduleDefinition(
            name="my-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        state.add_schedule(schedule1)

        # Add schedule with uppercase name (should be normalized to lowercase)
        schedule2 = ScheduleDefinition(
            name="MY-SCHEDULE",
            target=ScheduleTarget.SERIES,
            trigger=IntervalTrigger(hours=12),
        )
        state.add_schedule(schedule2)

        # Should still have only one schedule (names are normalized to lowercase)
        assert len(state.dynamic_schedules) == 1
        assert state.dynamic_schedules[0].target == ScheduleTarget.SERIES


class TestSchedulerStateRemoveSchedule:
    """Tests for SchedulerState.remove_schedule() method."""

    def test_remove_schedule_exists(self) -> None:
        """Test removing an existing schedule returns True."""
        state = SchedulerState()
        schedule = ScheduleDefinition(
            name="to-remove",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        state.add_schedule(schedule)

        result = state.remove_schedule("to-remove")

        assert result is True
        assert len(state.dynamic_schedules) == 0

    def test_remove_schedule_not_exists(self) -> None:
        """Test removing a non-existent schedule returns False."""
        state = SchedulerState()

        result = state.remove_schedule("nonexistent")

        assert result is False

    def test_remove_schedule_case_insensitive(self) -> None:
        """Test that schedule removal is case-insensitive."""
        state = SchedulerState()
        schedule = ScheduleDefinition(
            name="my-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        state.add_schedule(schedule)

        # Remove with different case
        result = state.remove_schedule("MY-SCHEDULE")

        assert result is True
        assert len(state.dynamic_schedules) == 0


class TestSchedulerStateGetSchedule:
    """Tests for SchedulerState.get_schedule() method."""

    def test_get_schedule_exists(self) -> None:
        """Test getting an existing schedule."""
        state = SchedulerState()
        schedule = ScheduleDefinition(
            name="my-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        state.add_schedule(schedule)

        result = state.get_schedule("my-schedule")

        assert result is not None
        assert result.name == "my-schedule"

    def test_get_schedule_not_exists(self) -> None:
        """Test getting a non-existent schedule returns None."""
        state = SchedulerState()

        result = state.get_schedule("nonexistent")

        assert result is None

    def test_get_schedule_case_insensitive(self) -> None:
        """Test that schedule lookup is case-insensitive."""
        state = SchedulerState()
        schedule = ScheduleDefinition(
            name="my-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        state.add_schedule(schedule)

        # Get with different case
        result = state.get_schedule("MY-SCHEDULE")

        assert result is not None
        assert result.name == "my-schedule"


class TestSchedulerStateAddRunRecord:
    """Tests for SchedulerState.add_run_record() method."""

    def test_add_run_record(self) -> None:
        """Test adding a run record."""
        state = SchedulerState()
        record = ScheduleRunRecord(
            schedule_name="test-schedule",
            started_at=datetime.now(UTC),
            status=RunStatus.COMPLETED,
            items_processed=10,
            items_with_4k=5,
        )

        state.add_run_record(record)

        assert len(state.schedule_history) == 1
        assert state.schedule_history[0].schedule_name == "test-schedule"

    def test_add_multiple_run_records(self) -> None:
        """Test adding multiple run records."""
        state = SchedulerState()

        for i in range(3):
            record = ScheduleRunRecord(
                schedule_name=f"schedule-{i}",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        assert len(state.schedule_history) == 3


class TestSchedulerStatePruneHistory:
    """Tests for SchedulerState.prune_history() method."""

    def test_prune_history_no_pruning_needed(self) -> None:
        """Test pruning when history is under the limit."""
        state = SchedulerState()

        for i in range(3):
            record = ScheduleRunRecord(
                schedule_name=f"schedule-{i}",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        removed = state.prune_history(limit=10)

        assert removed == 0
        assert len(state.schedule_history) == 3

    def test_prune_history_at_limit(self) -> None:
        """Test pruning when history is exactly at the limit."""
        state = SchedulerState()

        for i in range(5):
            record = ScheduleRunRecord(
                schedule_name=f"schedule-{i}",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        removed = state.prune_history(limit=5)

        assert removed == 0
        assert len(state.schedule_history) == 5

    def test_prune_history_over_limit(self) -> None:
        """Test pruning when history exceeds the limit."""
        state = SchedulerState()

        for i in range(10):
            record = ScheduleRunRecord(
                schedule_name=f"schedule-{i}",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        removed = state.prune_history(limit=3)

        assert removed == 7
        assert len(state.schedule_history) == 3
        # Should keep the most recent entries (last 3)
        assert state.schedule_history[0].schedule_name == "schedule-7"
        assert state.schedule_history[1].schedule_name == "schedule-8"
        assert state.schedule_history[2].schedule_name == "schedule-9"

    def test_prune_history_empty(self) -> None:
        """Test pruning an empty history."""
        state = SchedulerState()

        removed = state.prune_history(limit=10)

        assert removed == 0
        assert len(state.schedule_history) == 0


class TestSchedulerStateGetHistory:
    """Tests for SchedulerState.get_history() method."""

    def test_get_history_all(self) -> None:
        """Test getting all history."""
        state = SchedulerState()

        for i in range(3):
            record = ScheduleRunRecord(
                schedule_name=f"schedule-{i}",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        history = state.get_history()

        # Should be returned in reverse order (most recent first)
        assert len(history) == 3
        assert history[0].schedule_name == "schedule-2"
        assert history[1].schedule_name == "schedule-1"
        assert history[2].schedule_name == "schedule-0"

    def test_get_history_with_schedule_name_filter(self) -> None:
        """Test getting history filtered by schedule name."""
        state = SchedulerState()

        # Add records for two different schedules
        for _ in range(3):
            record = ScheduleRunRecord(
                schedule_name="schedule-a",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        for _ in range(2):
            record = ScheduleRunRecord(
                schedule_name="schedule-b",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        history = state.get_history(schedule_name="schedule-a")

        assert len(history) == 3
        for record in history:
            assert record.schedule_name == "schedule-a"

    def test_get_history_with_limit(self) -> None:
        """Test getting history with a limit."""
        state = SchedulerState()

        for i in range(10):
            record = ScheduleRunRecord(
                schedule_name=f"schedule-{i}",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        history = state.get_history(limit=3)

        assert len(history) == 3
        # Should be the most recent 3
        assert history[0].schedule_name == "schedule-9"
        assert history[1].schedule_name == "schedule-8"
        assert history[2].schedule_name == "schedule-7"

    def test_get_history_with_filter_and_limit(self) -> None:
        """Test getting history with both filter and limit."""
        state = SchedulerState()

        for i in range(10):
            record = ScheduleRunRecord(
                schedule_name="target-schedule",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
                items_processed=i,
            )
            state.add_run_record(record)

        # Add some other records
        for _ in range(5):
            record = ScheduleRunRecord(
                schedule_name="other-schedule",
                started_at=datetime.now(UTC),
                status=RunStatus.COMPLETED,
            )
            state.add_run_record(record)

        history = state.get_history(schedule_name="target-schedule", limit=3)

        assert len(history) == 3
        for record in history:
            assert record.schedule_name == "target-schedule"
        # Should be the most recent 3 of the filtered results
        assert history[0].items_processed == 9
        assert history[1].items_processed == 8
        assert history[2].items_processed == 7

    def test_get_history_empty(self) -> None:
        """Test getting history when empty."""
        state = SchedulerState()

        history = state.get_history()

        assert history == []

    def test_get_history_filter_no_matches(self) -> None:
        """Test getting history when filter matches nothing."""
        state = SchedulerState()

        record = ScheduleRunRecord(
            schedule_name="some-schedule",
            started_at=datetime.now(UTC),
            status=RunStatus.COMPLETED,
        )
        state.add_run_record(record)

        history = state.get_history(schedule_name="nonexistent")

        assert history == []


def _make_croniter_import_raiser(original_modules: dict[str, object]) -> object:
    """Create a fake import function that raises ImportError for croniter."""

    def fake_import(name: str, *_args: object, **_kwargs: object) -> object:
        if name == "croniter":
            raise ImportError("No module named 'croniter'")
        return original_modules.get(name)

    return fake_import


class TestCronTriggerValidationFallback:
    """Tests for CronTrigger validation when croniter is not installed."""

    def test_cron_trigger_validation_without_croniter_valid(self) -> None:
        """Test CronTrigger validation falls back to basic check when croniter unavailable."""
        original_modules = sys.modules.copy()

        try:
            if "croniter" in sys.modules:
                del sys.modules["croniter"]

            fake_import = _make_croniter_import_raiser(original_modules)
            with (
                patch.dict(sys.modules, {"croniter": None}),
                patch("builtins.__import__", side_effect=fake_import),
            ):
                # Valid 5-field cron expression should pass
                trigger = CronTrigger(expression="0 3 * * *")
                assert trigger.expression == "0 3 * * *"
        finally:
            sys.modules.update(original_modules)

    def test_cron_trigger_validation_without_croniter_invalid_field_count(self) -> None:
        """Test CronTrigger validation rejects wrong field count when croniter unavailable."""
        original_modules = sys.modules.copy()

        try:
            if "croniter" in sys.modules:
                del sys.modules["croniter"]

            fake_import = _make_croniter_import_raiser(original_modules)
            with (
                patch.dict(sys.modules, {"croniter": None}),
                patch("builtins.__import__", side_effect=fake_import),
                pytest.raises(ValueError, match="expected 5 fields"),
            ):
                # Invalid: only 4 fields (need 9+ chars to pass min_length)
                CronTrigger(expression="** ** ** **")
        finally:
            sys.modules.update(original_modules)

    def test_cron_trigger_validation_without_croniter_too_many_fields(self) -> None:
        """Test CronTrigger validation rejects too many fields when croniter unavailable."""
        original_modules = sys.modules.copy()

        try:
            if "croniter" in sys.modules:
                del sys.modules["croniter"]

            fake_import = _make_croniter_import_raiser(original_modules)
            with (
                patch.dict(sys.modules, {"croniter": None}),
                patch("builtins.__import__", side_effect=fake_import),
                pytest.raises(ValueError, match="expected 5 fields, got 7"),
            ):
                # Invalid: 7 fields (too many)
                CronTrigger(expression="0 3 * * * * *")
        finally:
            sys.modules.update(original_modules)
