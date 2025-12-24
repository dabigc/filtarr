"""Scheduler module for scheduled batch operations.

This module provides scheduling capabilities for filtarr batch operations,
allowing automatic 4K availability checks on configurable schedules.

Example:
    Configure schedules in config.toml::

        [scheduler]
        enabled = true

        [[scheduler.schedules]]
        name = "daily-movies"
        target = "movies"
        trigger = { type = "cron", expression = "0 3 * * *" }

    Or manage dynamically via CLI::

        filtarr schedule add daily-movies --target movies --cron "0 3 * * *"
        filtarr schedule list
        filtarr schedule run daily-movies
"""

from filtarr.scheduler.executor import JobExecutor, execute_schedule
from filtarr.scheduler.exporter import export_cron, export_systemd, export_systemd_timer
from filtarr.scheduler.manager import SchedulerManager
from filtarr.scheduler.models import (
    CronTrigger,
    IntervalTrigger,
    RunStatus,
    ScheduleDefinition,
    SchedulerState,
    ScheduleRunRecord,
    ScheduleTarget,
    SeriesStrategy,
    Trigger,
    TriggerType,
)
from filtarr.scheduler.triggers import (
    format_trigger_description,
    get_next_run_time,
    parse_interval_string,
    parse_trigger,
    trigger_to_cron_expression,
)

__all__ = [
    "CronTrigger",
    "IntervalTrigger",
    "JobExecutor",
    "RunStatus",
    "ScheduleDefinition",
    "ScheduleRunRecord",
    "ScheduleTarget",
    "SchedulerManager",
    "SchedulerState",
    "SeriesStrategy",
    "Trigger",
    "TriggerType",
    "execute_schedule",
    "export_cron",
    "export_systemd",
    "export_systemd_timer",
    "format_trigger_description",
    "get_next_run_time",
    "parse_interval_string",
    "parse_trigger",
    "trigger_to_cron_expression",
]
