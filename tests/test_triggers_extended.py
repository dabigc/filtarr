"""Extended tests for trigger parsing and conversion functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from filtarr.scheduler.models import CronTrigger, IntervalTrigger
from filtarr.scheduler.triggers import (
    format_trigger_description,
    parse_interval_string,
    parse_trigger,
    trigger_to_apscheduler,
    trigger_to_cron_expression,
)


class TestParseTriggerEdgeCases:
    """Tests for parse_trigger() edge cases."""

    def test_parse_trigger_cron_missing_expression(self) -> None:
        """Test that cron trigger without expression raises ValueError."""
        data = {"type": "cron"}

        with pytest.raises(ValueError, match="Cron trigger requires 'expression' field"):
            parse_trigger(data)

    def test_parse_trigger_cron_empty_expression(self) -> None:
        """Test that cron trigger with empty expression raises ValueError."""
        data = {"type": "cron", "expression": ""}

        with pytest.raises(ValueError, match="Cron trigger requires 'expression' field"):
            parse_trigger(data)

    def test_parse_trigger_cron_none_expression(self) -> None:
        """Test that cron trigger with None expression raises ValueError."""
        data = {"type": "cron", "expression": None}

        with pytest.raises(ValueError, match="Cron trigger requires 'expression' field"):
            parse_trigger(data)


class TestParseIntervalStringFullWords:
    """Tests for parse_interval_string() with full word units."""

    def test_parse_interval_string_minute(self) -> None:
        """Test parsing interval with 'minute' singular."""
        trigger = parse_interval_string("1 minute")
        assert trigger.minutes == 1
        assert trigger.hours == 0

    def test_parse_interval_string_minutes(self) -> None:
        """Test parsing interval with 'minutes' plural."""
        trigger = parse_interval_string("30 minutes")
        assert trigger.minutes == 30

    def test_parse_interval_string_day(self) -> None:
        """Test parsing interval with 'day' singular."""
        trigger = parse_interval_string("1 day")
        assert trigger.days == 1
        assert trigger.hours == 0

    def test_parse_interval_string_days(self) -> None:
        """Test parsing interval with 'days' plural."""
        trigger = parse_interval_string("7 days")
        assert trigger.days == 7

    def test_parse_interval_string_week(self) -> None:
        """Test parsing interval with 'week' singular."""
        trigger = parse_interval_string("1 week")
        assert trigger.weeks == 1
        assert trigger.days == 0

    def test_parse_interval_string_weeks(self) -> None:
        """Test parsing interval with 'weeks' plural."""
        trigger = parse_interval_string("2 weeks")
        assert trigger.weeks == 2

    def test_parse_interval_string_second(self) -> None:
        """Test parsing interval with 'second' singular."""
        trigger = parse_interval_string("1 second")
        assert trigger.seconds == 1

    def test_parse_interval_string_seconds(self) -> None:
        """Test parsing interval with 'seconds' plural."""
        trigger = parse_interval_string("45 seconds")
        assert trigger.seconds == 45

    def test_parse_interval_string_hour(self) -> None:
        """Test parsing interval with 'hour' singular."""
        trigger = parse_interval_string("1 hour")
        assert trigger.hours == 1

    def test_parse_interval_string_hours(self) -> None:
        """Test parsing interval with 'hours' plural."""
        trigger = parse_interval_string("6 hours")
        assert trigger.hours == 6

    def test_parse_interval_string_case_insensitive(self) -> None:
        """Test that parsing is case-insensitive."""
        trigger = parse_interval_string("5 MINUTES")
        assert trigger.minutes == 5

    def test_parse_interval_string_with_extra_whitespace(self) -> None:
        """Test parsing with extra whitespace."""
        trigger = parse_interval_string("  10  minutes  ")
        assert trigger.minutes == 10


class TestTriggerToApscheduler:
    """Tests for trigger_to_apscheduler() function."""

    def test_trigger_to_apscheduler_interval(self) -> None:
        """Test converting IntervalTrigger to APScheduler trigger."""
        trigger = IntervalTrigger(hours=6, minutes=30)

        mock_interval_trigger = MagicMock()
        mock_cron_trigger = MagicMock()

        with (
            patch.dict(
                "sys.modules",
                {
                    "apscheduler": MagicMock(),
                    "apscheduler.triggers": MagicMock(),
                    "apscheduler.triggers.interval": MagicMock(),
                    "apscheduler.triggers.cron": MagicMock(),
                },
            ),
            patch(
                "apscheduler.triggers.interval.IntervalTrigger",
                mock_interval_trigger,
            ),
            patch(
                "apscheduler.triggers.cron.CronTrigger",
                mock_cron_trigger,
            ),
        ):
            trigger_to_apscheduler(trigger)

            mock_interval_trigger.assert_called_once_with(
                weeks=0,
                days=0,
                hours=6,
                minutes=30,
                seconds=0,
            )

    def test_trigger_to_apscheduler_cron(self) -> None:
        """Test converting CronTrigger to APScheduler trigger."""
        trigger = CronTrigger(expression="0 3 * * *")

        mock_cron_trigger = MagicMock()
        mock_cron_trigger.from_crontab = MagicMock(return_value=MagicMock())

        with (
            patch.dict(
                "sys.modules",
                {
                    "apscheduler": MagicMock(),
                    "apscheduler.triggers": MagicMock(),
                    "apscheduler.triggers.interval": MagicMock(),
                    "apscheduler.triggers.cron": MagicMock(),
                },
            ),
            patch(
                "apscheduler.triggers.cron.CronTrigger",
                mock_cron_trigger,
            ),
        ):
            trigger_to_apscheduler(trigger)

            mock_cron_trigger.from_crontab.assert_called_once_with("0 3 * * *")


class TestTriggerToCronExpression:
    """Tests for trigger_to_cron_expression() edge cases."""

    def test_cron_trigger_passthrough(self) -> None:
        """Test that CronTrigger expression is returned unchanged."""
        trigger = CronTrigger(expression="0 3 * * *")
        result = trigger_to_cron_expression(trigger)
        assert result == "0 3 * * *"

    def test_sub_minute_interval(self) -> None:
        """Test that sub-minute intervals are rounded up to 1 minute."""
        # Only seconds, no minutes or higher - rounds up to 1 minute
        trigger = IntervalTrigger(seconds=30)
        result = trigger_to_cron_expression(trigger)
        # Seconds > 0 adds 1 to total_minutes, so 0 + 1 = 1 minute
        assert result == "*/1 * * * *"

    def test_sub_minute_interval_small_seconds(self) -> None:
        """Test that very small second intervals are rounded up to 1 minute."""
        trigger = IntervalTrigger(seconds=5)
        result = trigger_to_cron_expression(trigger)
        # Seconds > 0 adds 1 to total_minutes, so 0 + 1 = 1 minute
        assert result == "*/1 * * * *"

    def test_minute_interval(self) -> None:
        """Test minute interval conversion."""
        trigger = IntervalTrigger(minutes=15)
        result = trigger_to_cron_expression(trigger)
        assert result == "*/15 * * * *"

    def test_hourly_interval(self) -> None:
        """Test hourly interval conversion."""
        trigger = IntervalTrigger(hours=4)
        result = trigger_to_cron_expression(trigger)
        assert result == "0 */4 * * *"

    def test_daily_interval(self) -> None:
        """Test daily interval conversion."""
        trigger = IntervalTrigger(days=2)
        result = trigger_to_cron_expression(trigger)
        assert result == "0 0 */2 * *"

    def test_daily_interval_single_day(self) -> None:
        """Test single day interval conversion."""
        trigger = IntervalTrigger(days=1)
        result = trigger_to_cron_expression(trigger)
        assert result == "0 0 */1 * *"

    def test_weekly_interval(self) -> None:
        """Test weekly interval conversion."""
        trigger = IntervalTrigger(weeks=1)
        result = trigger_to_cron_expression(trigger)
        assert result == "0 0 * * 0"

    def test_multi_week_interval(self) -> None:
        """Test multi-week interval defaults to weekly cron."""
        trigger = IntervalTrigger(weeks=2)
        result = trigger_to_cron_expression(trigger)
        # Weekly or longer returns weekly cron
        assert result == "0 0 * * 0"

    def test_mixed_days_hours(self) -> None:
        """Test mixed days and hours interval."""
        trigger = IntervalTrigger(days=3, hours=12)
        result = trigger_to_cron_expression(trigger)
        # 3 days + 12 hours = 84 hours = 5040 minutes
        # 5040 / (24*60) = 3.5 days, should round to 3 or 4 days
        # Since it's between 1-7 days (< weekly), should use daily format
        assert result == "0 0 */3 * *"

    def test_seconds_rounds_up_to_minute(self) -> None:
        """Test that seconds > 0 rounds up when combined with minutes."""
        trigger = IntervalTrigger(minutes=5, seconds=30)
        result = trigger_to_cron_expression(trigger)
        # 5 minutes + 30 seconds rounds up to 6 minutes
        assert result == "*/6 * * * *"


class TestFormatTriggerDescription:
    """Tests for format_trigger_description() function."""

    def test_format_cron_trigger(self) -> None:
        """Test formatting a cron trigger."""
        trigger = CronTrigger(expression="0 3 * * *")
        result = format_trigger_description(trigger)
        assert result == "cron: 0 3 * * *"

    def test_format_interval_hours(self) -> None:
        """Test formatting an interval with hours."""
        trigger = IntervalTrigger(hours=6)
        result = format_trigger_description(trigger)
        assert result == "every 6h"

    def test_format_interval_minutes(self) -> None:
        """Test formatting an interval with minutes."""
        trigger = IntervalTrigger(minutes=30)
        result = format_trigger_description(trigger)
        assert result == "every 30m"

    def test_format_interval_seconds(self) -> None:
        """Test formatting an interval with seconds."""
        trigger = IntervalTrigger(seconds=45)
        result = format_trigger_description(trigger)
        assert result == "every 45s"

    def test_format_interval_days(self) -> None:
        """Test formatting an interval with days."""
        trigger = IntervalTrigger(days=2)
        result = format_trigger_description(trigger)
        assert result == "every 2d"

    def test_format_interval_weeks(self) -> None:
        """Test formatting an interval with weeks."""
        trigger = IntervalTrigger(weeks=1)
        result = format_trigger_description(trigger)
        assert result == "every 1w"

    def test_format_interval_days_and_hours(self) -> None:
        """Test formatting an interval with days and hours."""
        trigger = IntervalTrigger(days=1, hours=12)
        result = format_trigger_description(trigger)
        assert result == "every 1d12h"

    def test_format_interval_hours_and_minutes(self) -> None:
        """Test formatting an interval with hours and minutes."""
        trigger = IntervalTrigger(hours=2, minutes=30)
        result = format_trigger_description(trigger)
        assert result == "every 2h30m"

    def test_format_interval_days_and_seconds(self) -> None:
        """Test formatting an interval with days and seconds."""
        trigger = IntervalTrigger(days=1, seconds=30)
        result = format_trigger_description(trigger)
        assert result == "every 1d30s"

    def test_format_interval_all_components(self) -> None:
        """Test formatting an interval with all components."""
        trigger = IntervalTrigger(weeks=1, days=2, hours=3, minutes=4, seconds=5)
        result = format_trigger_description(trigger)
        assert result == "every 1w2d3h4m5s"

    def test_format_interval_weeks_and_days(self) -> None:
        """Test formatting an interval with weeks and days."""
        trigger = IntervalTrigger(weeks=2, days=3)
        result = format_trigger_description(trigger)
        assert result == "every 2w3d"
