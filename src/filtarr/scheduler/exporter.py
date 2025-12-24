"""Export schedules to external scheduler formats (cron, systemd)."""

from __future__ import annotations

import shutil
from datetime import datetime
from typing import TYPE_CHECKING

from filtarr.scheduler.models import CronTrigger, IntervalTrigger, ScheduleDefinition
from filtarr.scheduler.triggers import trigger_to_cron_expression

if TYPE_CHECKING:
    from pathlib import Path


def _get_filtarr_path() -> str:
    """Get the path to the filtarr executable."""
    # Try to find filtarr in PATH
    filtarr_path = shutil.which("filtarr")
    if filtarr_path:
        return filtarr_path
    # Fallback to generic command
    return "filtarr"


def _schedule_to_batch_args(schedule: ScheduleDefinition) -> str:
    """Convert schedule definition to check batch CLI arguments.

    Args:
        schedule: Schedule definition

    Returns:
        CLI arguments string
    """
    args = ["check", "batch"]

    # Target type
    if schedule.target.value == "movies":
        args.append("--all-movies")
    elif schedule.target.value == "series":
        args.append("--all-series")
    else:  # both
        args.extend(["--all-movies", "--all-series"])

    # Batch parameters
    if schedule.batch_size > 0:
        args.extend(["--batch-size", str(schedule.batch_size)])

    if schedule.delay != 0.5:  # Only include if not default
        args.extend(["--delay", str(schedule.delay)])

    if not schedule.skip_tagged:
        args.append("--no-skip-tagged")

    if not schedule.include_rechecks:
        args.append("--no-include-rechecks")

    if schedule.no_tag:
        args.append("--no-tag")

    # Series-specific
    if schedule.target.value in ("series", "both"):
        if schedule.strategy.value != "recent":  # Only include if not default
            args.extend(["--strategy", schedule.strategy.value])
        if schedule.seasons != 3:  # Only include if not default
            args.extend(["--seasons", str(schedule.seasons)])

    return " ".join(args)


def export_cron(
    schedules: list[ScheduleDefinition],
    filtarr_path: str | None = None,
) -> str:
    """Export schedules to cron format.

    Args:
        schedules: List of schedule definitions
        filtarr_path: Path to filtarr executable (auto-detected if None)

    Returns:
        Crontab content string
    """
    if filtarr_path is None:
        filtarr_path = _get_filtarr_path()

    lines = [
        "# filtarr scheduled batch operations",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "# Add these lines to your crontab (crontab -e)",
        "",
        "# Environment setup (adjust as needed)",
        "# PATH=/usr/local/bin:/usr/bin:/bin",
        "# FILTARR_RADARR_URL=http://localhost:7878",
        "# FILTARR_RADARR_API_KEY=your-api-key",
        "",
    ]

    enabled_schedules = [s for s in schedules if s.enabled]

    if not enabled_schedules:
        lines.append("# No enabled schedules found")
        return "\n".join(lines)

    for schedule in enabled_schedules:
        cron_expr = trigger_to_cron_expression(schedule.trigger)
        batch_args = _schedule_to_batch_args(schedule)
        command = f"{filtarr_path} {batch_args}"

        lines.extend(
            [
                f"# Schedule: {schedule.name}",
                f"# Target: {schedule.target.value}",
                f"{cron_expr} {command}",
                "",
            ]
        )

    return "\n".join(lines)


def export_systemd_timer(
    schedule: ScheduleDefinition,
    filtarr_path: str | None = None,
) -> tuple[str, str]:
    """Export a single schedule to systemd timer and service files.

    Args:
        schedule: Schedule definition
        filtarr_path: Path to filtarr executable (auto-detected if None)

    Returns:
        Tuple of (timer_content, service_content)
    """
    if filtarr_path is None:
        filtarr_path = _get_filtarr_path()

    batch_args = _schedule_to_batch_args(schedule)

    # Convert trigger to systemd OnCalendar format
    on_calendar = _trigger_to_systemd_calendar(schedule.trigger)

    timer_content = f"""# /etc/systemd/system/filtarr-{schedule.name}.timer
# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
#
# Install:
#   sudo cp filtarr-{schedule.name}.timer /etc/systemd/system/
#   sudo cp filtarr-{schedule.name}.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now filtarr-{schedule.name}.timer

[Unit]
Description=Filtarr scheduled batch check: {schedule.name}

[Timer]
OnCalendar={on_calendar}
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
"""

    service_content = f"""# /etc/systemd/system/filtarr-{schedule.name}.service
# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

[Unit]
Description=Filtarr batch check: {schedule.name}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={filtarr_path} {batch_args}
# Uncomment and configure environment variables:
# Environment="FILTARR_RADARR_URL=http://localhost:7878"
# Environment="FILTARR_RADARR_API_KEY=your-api-key"
# Or use an environment file:
# EnvironmentFile=/etc/filtarr/env

[Install]
WantedBy=multi-user.target
"""

    return timer_content, service_content


def _trigger_to_systemd_calendar(trigger: IntervalTrigger | CronTrigger) -> str:
    """Convert trigger to systemd OnCalendar format.

    Args:
        trigger: Trigger definition

    Returns:
        systemd OnCalendar expression
    """
    if isinstance(trigger, CronTrigger):
        # Convert cron to systemd calendar
        # Cron: minute hour day month weekday
        # Systemd: DayOfWeek Year-Month-Day Hour:Minute:Second
        parts = trigger.expression.split()
        if len(parts) != 5:
            return "*-*-* *:*:00"  # Fallback

        minute, hour, day, month, weekday = parts

        # Handle weekday (cron 0-7 where 0,7=Sunday, systemd uses names)
        weekday_map = {
            "*": "*",
            "0": "Sun",
            "1": "Mon",
            "2": "Tue",
            "3": "Wed",
            "4": "Thu",
            "5": "Fri",
            "6": "Sat",
            "7": "Sun",
        }
        systemd_weekday = weekday_map.get(weekday, "*")

        # Build calendar spec
        date_part = f"*-{month}-{day}" if month != "*" or day != "*" else "*-*-*"
        time_part = f"{hour}:{minute}:00"

        if systemd_weekday != "*":
            return f"{systemd_weekday} {date_part} {time_part}"
        return f"{date_part} {time_part}"

    else:
        # Interval trigger
        total_seconds = trigger.total_seconds()

        if total_seconds < 60:
            return f"*-*-* *:*:00/{total_seconds}"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"*-*-* *:00/{minutes}:00"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"*-*-* 00/{hours}:00:00"
        elif total_seconds < 604800:
            days = total_seconds // 86400
            return f"*-*-01/{days} 00:00:00"
        else:
            # Weekly or longer
            return "Sun *-*-* 00:00:00"


def export_systemd(
    schedules: list[ScheduleDefinition],
    output_dir: Path | None = None,
    filtarr_path: str | None = None,
) -> list[tuple[str, str, str]]:
    """Export all schedules to systemd format.

    Args:
        schedules: List of schedule definitions
        output_dir: Directory to write files to (None for dry-run/display)
        filtarr_path: Path to filtarr executable (auto-detected if None)

    Returns:
        List of (schedule_name, timer_content, service_content) tuples
    """
    results = []
    enabled_schedules = [s for s in schedules if s.enabled]

    for schedule in enabled_schedules:
        timer_content, service_content = export_systemd_timer(schedule, filtarr_path)
        results.append((schedule.name, timer_content, service_content))

        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            timer_path = output_dir / f"filtarr-{schedule.name}.timer"
            service_path = output_dir / f"filtarr-{schedule.name}.service"

            timer_path.write_text(timer_content)
            service_path.write_text(service_content)

    return results
