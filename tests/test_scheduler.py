"""Tests for the scheduler module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from findarr.scheduler import (
    CronTrigger,
    IntervalTrigger,
    RunStatus,
    ScheduleDefinition,
    ScheduleRunRecord,
    ScheduleTarget,
    SeriesStrategy,
    TriggerType,
    format_trigger_description,
    get_next_run_time,
    parse_interval_string,
    parse_trigger,
    trigger_to_cron_expression,
)


class TestIntervalTrigger:
    """Tests for IntervalTrigger model."""

    def test_interval_trigger_valid(self) -> None:
        """Test creating a valid interval trigger."""
        trigger = IntervalTrigger(hours=6)
        assert trigger.type == TriggerType.INTERVAL
        assert trigger.hours == 6
        assert trigger.minutes == 0

    def test_interval_trigger_compound(self) -> None:
        """Test compound interval trigger."""
        trigger = IntervalTrigger(hours=2, minutes=30)
        assert trigger.hours == 2
        assert trigger.minutes == 30
        assert trigger.total_seconds() == 2 * 3600 + 30 * 60

    def test_interval_trigger_all_zeros_fails(self) -> None:
        """Test that all-zero interval fails validation."""
        with pytest.raises(ValueError, match="At least one interval component"):
            IntervalTrigger()

    def test_interval_trigger_total_seconds(self) -> None:
        """Test total_seconds calculation."""
        trigger = IntervalTrigger(weeks=1, days=2, hours=3, minutes=4, seconds=5)
        expected = (
            1 * 7 * 24 * 3600  # weeks
            + 2 * 24 * 3600  # days
            + 3 * 3600  # hours
            + 4 * 60  # minutes
            + 5  # seconds
        )
        assert trigger.total_seconds() == expected


class TestCronTrigger:
    """Tests for CronTrigger model."""

    def test_cron_trigger_valid(self) -> None:
        """Test creating a valid cron trigger."""
        trigger = CronTrigger(expression="0 3 * * *")
        assert trigger.type == TriggerType.CRON
        assert trigger.expression == "0 3 * * *"

    def test_cron_trigger_invalid_format(self) -> None:
        """Test that invalid cron expression fails."""
        with pytest.raises((ValueError, Exception)):
            CronTrigger(expression="invalid")


class TestScheduleDefinition:
    """Tests for ScheduleDefinition model."""

    def test_schedule_definition_minimal(self) -> None:
        """Test creating a schedule with minimal fields."""
        schedule = ScheduleDefinition(
            name="test-schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )
        assert schedule.name == "test-schedule"
        assert schedule.target == ScheduleTarget.MOVIES
        assert schedule.enabled is True
        assert schedule.batch_size == 0
        assert schedule.delay == 0.5

    def test_schedule_definition_full(self) -> None:
        """Test creating a schedule with all fields."""
        schedule = ScheduleDefinition(
            name="full-schedule",
            enabled=False,
            target=ScheduleTarget.BOTH,
            trigger=CronTrigger(expression="0 3 * * 0"),
            batch_size=100,
            delay=1.0,
            skip_tagged=False,
            include_rechecks=False,
            no_tag=True,
            dry_run=True,
            strategy=SeriesStrategy.DISTRIBUTED,
            seasons=5,
        )
        assert schedule.name == "full-schedule"
        assert schedule.enabled is False
        assert schedule.batch_size == 100
        assert schedule.strategy == SeriesStrategy.DISTRIBUTED
        assert schedule.seasons == 5

    def test_schedule_name_normalized(self) -> None:
        """Test that schedule name is normalized to lowercase."""
        schedule = ScheduleDefinition(
            name="My-Schedule",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=1),
        )
        assert schedule.name == "my-schedule"

    def test_schedule_name_invalid_chars(self) -> None:
        """Test that invalid characters in name fail validation."""
        with pytest.raises(ValueError):
            ScheduleDefinition(
                name="my schedule!",
                target=ScheduleTarget.MOVIES,
                trigger=IntervalTrigger(hours=1),
            )


class TestScheduleRunRecord:
    """Tests for ScheduleRunRecord model."""

    def test_run_record_completed(self) -> None:
        """Test creating a completed run record."""
        started = datetime.now(UTC)
        completed = started + timedelta(minutes=5)

        record = ScheduleRunRecord(
            schedule_name="test",
            started_at=started,
            completed_at=completed,
            status=RunStatus.COMPLETED,
            items_processed=100,
            items_with_4k=25,
        )

        assert record.status == RunStatus.COMPLETED
        assert record.items_processed == 100
        assert record.items_with_4k == 25
        assert record.duration_seconds() == pytest.approx(300, abs=1)

    def test_run_record_running(self) -> None:
        """Test running record has no duration."""
        record = ScheduleRunRecord(
            schedule_name="test",
            started_at=datetime.now(UTC),
            status=RunStatus.RUNNING,
        )
        assert record.duration_seconds() is None


class TestTriggerParsing:
    """Tests for trigger parsing functions."""

    def test_parse_trigger_interval(self) -> None:
        """Test parsing interval trigger from dict."""
        data = {"type": "interval", "hours": 6, "minutes": 30}
        trigger = parse_trigger(data)
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.hours == 6
        assert trigger.minutes == 30

    def test_parse_trigger_cron(self) -> None:
        """Test parsing cron trigger from dict."""
        data = {"type": "cron", "expression": "0 3 * * *"}
        trigger = parse_trigger(data)
        assert isinstance(trigger, CronTrigger)
        assert trigger.expression == "0 3 * * *"

    def test_parse_trigger_invalid_type(self) -> None:
        """Test parsing unknown trigger type fails."""
        with pytest.raises(ValueError, match="Unknown trigger type"):
            parse_trigger({"type": "unknown"})

    def test_parse_interval_string_hours(self) -> None:
        """Test parsing interval string with hours."""
        trigger = parse_interval_string("6h")
        assert trigger.hours == 6

    def test_parse_interval_string_compound(self) -> None:
        """Test parsing compound interval string."""
        trigger = parse_interval_string("2h30m")
        assert trigger.hours == 2
        assert trigger.minutes == 30

    def test_parse_interval_string_full_words(self) -> None:
        """Test parsing interval with full words."""
        trigger = parse_interval_string("30 minutes")
        assert trigger.minutes == 30

    def test_parse_interval_string_invalid(self) -> None:
        """Test parsing invalid interval string fails."""
        with pytest.raises(ValueError, match="Invalid interval format"):
            parse_interval_string("invalid")


class TestTriggerConversion:
    """Tests for trigger conversion functions."""

    def test_trigger_to_cron_from_cron(self) -> None:
        """Test cron trigger stays as-is."""
        trigger = CronTrigger(expression="0 3 * * *")
        assert trigger_to_cron_expression(trigger) == "0 3 * * *"

    def test_trigger_to_cron_from_hourly(self) -> None:
        """Test hourly interval converts to cron."""
        trigger = IntervalTrigger(hours=6)
        cron = trigger_to_cron_expression(trigger)
        assert "*/6" in cron or "0" in cron

    def test_format_trigger_description_cron(self) -> None:
        """Test formatting cron trigger description."""
        trigger = CronTrigger(expression="0 3 * * *")
        desc = format_trigger_description(trigger)
        assert desc == "cron: 0 3 * * *"

    def test_format_trigger_description_interval(self) -> None:
        """Test formatting interval trigger description."""
        trigger = IntervalTrigger(hours=6)
        desc = format_trigger_description(trigger)
        assert desc == "every 6h"

    def test_get_next_run_time_interval(self) -> None:
        """Test getting next run time for interval."""
        trigger = IntervalTrigger(hours=6)
        base = datetime.now(UTC)
        next_run = get_next_run_time(trigger, base)
        assert next_run > base
        assert (next_run - base).total_seconds() == pytest.approx(6 * 3600, abs=1)

    def test_get_next_run_time_cron(self) -> None:
        """Test getting next run time for cron."""
        trigger = CronTrigger(expression="0 3 * * *")
        next_run = get_next_run_time(trigger)
        # croniter returns naive datetimes, so compare to naive now
        assert next_run > datetime.now()
