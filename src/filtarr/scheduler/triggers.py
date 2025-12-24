"""Trigger parsing and utility functions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from filtarr.scheduler.models import (
    CronTrigger,
    IntervalTrigger,
    Trigger,
    TriggerType,
)

if TYPE_CHECKING:
    from apscheduler.triggers.base import BaseTrigger


def parse_trigger(data: dict[str, Any]) -> Trigger:
    """Parse a trigger from a dictionary.

    Args:
        data: Dictionary containing trigger configuration

    Returns:
        Parsed Trigger (IntervalTrigger or CronTrigger)

    Raises:
        ValueError: If trigger type is invalid or data is malformed
    """
    trigger_type = data.get("type")

    if trigger_type == TriggerType.INTERVAL or trigger_type == "interval":
        return IntervalTrigger(
            type=TriggerType.INTERVAL,
            weeks=data.get("weeks", 0),
            days=data.get("days", 0),
            hours=data.get("hours", 0),
            minutes=data.get("minutes", 0),
            seconds=data.get("seconds", 0),
        )
    elif trigger_type == TriggerType.CRON or trigger_type == "cron":
        expression = data.get("expression")
        if not expression:
            raise ValueError("Cron trigger requires 'expression' field")
        return CronTrigger(type=TriggerType.CRON, expression=expression)
    else:
        raise ValueError(f"Unknown trigger type: {trigger_type}")


def parse_interval_string(interval_str: str) -> IntervalTrigger:
    """Parse a human-readable interval string.

    Supported formats:
        - "30s", "30 seconds" -> 30 seconds
        - "5m", "5 minutes" -> 5 minutes
        - "2h", "2 hours" -> 2 hours
        - "1d", "1 day" -> 1 day
        - "1w", "1 week" -> 1 week
        - "2h30m" -> 2 hours 30 minutes (compound)

    Args:
        interval_str: Human-readable interval string

    Returns:
        IntervalTrigger with parsed values

    Raises:
        ValueError: If format is invalid
    """
    import re

    interval_str = interval_str.lower().strip()

    # Try compound format first (e.g., "2h30m")
    compound_pattern = r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?"
    match = re.fullmatch(compound_pattern, interval_str)
    if match and any(match.groups()):
        weeks = int(match.group(1) or 0)
        days = int(match.group(2) or 0)
        hours = int(match.group(3) or 0)
        minutes = int(match.group(4) or 0)
        seconds = int(match.group(5) or 0)

        if any([weeks, days, hours, minutes, seconds]):
            return IntervalTrigger(
                weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds
            )

    # Try single unit format (e.g., "30 seconds")
    single_pattern = r"(\d+)\s*(seconds?|minutes?|hours?|days?|weeks?|s|m|h|d|w)"
    match = re.fullmatch(single_pattern, interval_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)

        if unit in ("s", "second", "seconds"):
            return IntervalTrigger(seconds=value)
        elif unit in ("m", "minute", "minutes"):
            return IntervalTrigger(minutes=value)
        elif unit in ("h", "hour", "hours"):
            return IntervalTrigger(hours=value)
        elif unit in ("d", "day", "days"):
            return IntervalTrigger(days=value)
        elif unit in ("w", "week", "weeks"):
            return IntervalTrigger(weeks=value)

    raise ValueError(
        f"Invalid interval format: {interval_str}. "
        "Use formats like '30s', '5m', '2h', '1d', '1w', or compound like '2h30m'"
    )


def get_next_run_time(trigger: Trigger, base_time: datetime | None = None) -> datetime:
    """Calculate the next run time for a trigger.

    Args:
        trigger: The trigger to calculate next run for
        base_time: Base time to calculate from (default: now)

    Returns:
        Next scheduled run time
    """
    from croniter import croniter

    if base_time is None:
        base_time = datetime.now()

    if isinstance(trigger, CronTrigger):
        cron = croniter(trigger.expression, base_time)
        next_time: datetime = cron.get_next(datetime)
        return next_time
    else:
        # For interval triggers, next run is base_time + interval
        from datetime import timedelta

        delta = timedelta(
            weeks=trigger.weeks,
            days=trigger.days,
            hours=trigger.hours,
            minutes=trigger.minutes,
            seconds=trigger.seconds,
        )
        return base_time + delta


def trigger_to_apscheduler(trigger: Trigger) -> BaseTrigger:
    """Convert a Trigger to an APScheduler trigger.

    Args:
        trigger: The trigger to convert

    Returns:
        APScheduler trigger instance

    Raises:
        ImportError: If APScheduler is not installed
    """
    from apscheduler.triggers.cron import CronTrigger as APSCronTrigger
    from apscheduler.triggers.interval import IntervalTrigger as APSIntervalTrigger

    if isinstance(trigger, CronTrigger):
        return APSCronTrigger.from_crontab(trigger.expression)
    else:
        return APSIntervalTrigger(
            weeks=trigger.weeks,
            days=trigger.days,
            hours=trigger.hours,
            minutes=trigger.minutes,
            seconds=trigger.seconds,
        )


def trigger_to_cron_expression(trigger: Trigger) -> str:
    """Convert a trigger to a cron expression string.

    For interval triggers, this produces an approximate cron expression.
    Not all intervals can be perfectly represented in cron format.

    Args:
        trigger: The trigger to convert

    Returns:
        Cron expression string
    """
    if isinstance(trigger, CronTrigger):
        return trigger.expression

    # Convert interval to approximate cron
    # This is best-effort - not all intervals map cleanly to cron
    total_minutes = (
        trigger.weeks * 7 * 24 * 60
        + trigger.days * 24 * 60
        + trigger.hours * 60
        + trigger.minutes
        + (1 if trigger.seconds > 0 else 0)  # Round up seconds
    )

    if total_minutes == 0:
        # Sub-minute interval - run every minute
        return "* * * * *"
    elif total_minutes < 60:
        # Every N minutes
        return f"*/{total_minutes} * * * *"
    elif total_minutes < 24 * 60:
        # Every N hours
        hours = total_minutes // 60
        return f"0 */{hours} * * *"
    elif total_minutes < 7 * 24 * 60:
        # Every N days
        days = total_minutes // (24 * 60)
        return f"0 0 */{days} * *"
    else:
        # Weekly or longer - run weekly
        return "0 0 * * 0"


def format_trigger_description(trigger: Trigger) -> str:
    """Format a human-readable description of a trigger.

    Args:
        trigger: The trigger to describe

    Returns:
        Human-readable description
    """
    if isinstance(trigger, CronTrigger):
        return f"cron: {trigger.expression}"

    parts = []
    if trigger.weeks:
        parts.append(f"{trigger.weeks}w")
    if trigger.days:
        parts.append(f"{trigger.days}d")
    if trigger.hours:
        parts.append(f"{trigger.hours}h")
    if trigger.minutes:
        parts.append(f"{trigger.minutes}m")
    if trigger.seconds:
        parts.append(f"{trigger.seconds}s")

    return f"every {''.join(parts)}"
