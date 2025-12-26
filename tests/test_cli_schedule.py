"""Tests for CLI schedule commands."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from filtarr.cli import app
from filtarr.config import Config, RadarrConfig, SchedulerConfig, SonarrConfig
from filtarr.scheduler import (
    CronTrigger,
    IntervalTrigger,
    RunStatus,
    ScheduleDefinition,
    ScheduleRunRecord,
    ScheduleTarget,
    SeriesStrategy,
)

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _create_mock_config() -> Config:
    """Create a mock Config for schedule tests."""
    return Config(
        radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-key"),
        sonarr=SonarrConfig(url="http://localhost:8989", api_key="sonarr-key"),
        scheduler=SchedulerConfig(enabled=True, schedules=[]),
    )


def _create_mock_state_manager() -> MagicMock:
    """Create a mock StateManager for testing."""
    mock = MagicMock()
    mock.record_check = MagicMock()
    mock.get_stale_unavailable_items = MagicMock(return_value=[])
    mock.get_dynamic_schedules = MagicMock(return_value=[])
    mock.add_dynamic_schedule = MagicMock()
    mock.remove_dynamic_schedule = MagicMock(return_value=True)
    mock.update_dynamic_schedule = MagicMock(return_value=True)
    mock.get_schedule_history = MagicMock(return_value=[])
    mock.add_schedule_run = MagicMock()
    return mock


def _create_mock_scheduler_manager() -> MagicMock:
    """Create a mock SchedulerManager for testing."""
    mock = MagicMock()
    mock.get_all_schedules = MagicMock(return_value=[])
    mock.get_schedule = MagicMock(return_value=None)
    mock.add_schedule = MagicMock()
    mock.remove_schedule = MagicMock(return_value=True)
    mock.enable_schedule = MagicMock(return_value=True)
    mock.disable_schedule = MagicMock(return_value=True)
    mock.get_history = MagicMock(return_value=[])
    return mock


def _create_sample_schedule(
    name: str = "test-schedule",
    enabled: bool = True,
    target: ScheduleTarget = ScheduleTarget.MOVIES,
    source: str = "dynamic",
) -> ScheduleDefinition:
    """Create a sample schedule for testing."""
    return ScheduleDefinition(
        name=name,
        enabled=enabled,
        target=target,
        trigger=IntervalTrigger(hours=6),
        batch_size=100,
        delay=0.5,
        skip_tagged=True,
        strategy=SeriesStrategy.RECENT,
        seasons=3,
        source=source,  # type: ignore[arg-type]
    )


def _create_sample_cron_schedule(name: str = "cron-schedule") -> ScheduleDefinition:
    """Create a sample schedule with cron trigger."""
    return ScheduleDefinition(
        name=name,
        enabled=True,
        target=ScheduleTarget.BOTH,
        trigger=CronTrigger(expression="0 3 * * *"),
        source="config",  # type: ignore[arg-type]
    )


def _create_sample_run_record(
    schedule_name: str = "test-schedule",
    status: RunStatus = RunStatus.COMPLETED,
    items_processed: int = 50,
    items_with_4k: int = 10,
) -> ScheduleRunRecord:
    """Create a sample run record for testing."""
    now = datetime.now(UTC)
    return ScheduleRunRecord(
        schedule_name=schedule_name,
        started_at=now - timedelta(minutes=5),
        completed_at=now,
        status=status,
        items_processed=items_processed,
        items_with_4k=items_with_4k,
        errors=[],
    )


class TestScheduleList:
    """Tests for 'filtarr schedule list' command."""

    def test_schedule_list_no_schedules(self) -> None:
        """Should show message when no schedules configured."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = []

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "list"])

        assert result.exit_code == 0
        assert "No schedules configured" in result.output

    def test_schedule_list_with_schedules_table_format(self) -> None:
        """Should display schedules in table format."""
        schedules = [
            _create_sample_schedule("daily-movies", enabled=True, target=ScheduleTarget.MOVIES),
            _create_sample_schedule("weekly-series", enabled=False, target=ScheduleTarget.SERIES),
        ]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "list"])

        assert result.exit_code == 0
        assert "daily-movies" in result.output
        assert "weekly-series" in result.output
        assert "movies" in result.output
        assert "series" in result.output

    def test_schedule_list_json_format(self) -> None:
        """Should display schedules in JSON format."""
        schedules = [_create_sample_schedule("test-schedule")]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "list", "--format", "json"])

        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "test-schedule"

    def test_schedule_list_enabled_only(self) -> None:
        """Should filter to show only enabled schedules."""
        schedules = [
            _create_sample_schedule("enabled-schedule", enabled=True),
            _create_sample_schedule("disabled-schedule", enabled=False),
        ]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "list", "--enabled-only"])

        assert result.exit_code == 0
        assert "enabled-schedule" in result.output
        assert "disabled-schedule" not in result.output

    def test_schedule_list_with_cron_trigger(self) -> None:
        """Should display cron trigger information."""
        schedules = [_create_sample_cron_schedule("cron-schedule")]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "list"])

        assert result.exit_code == 0
        assert "cron-schedule" in result.output
        assert "cron:" in result.output or "0 3 * * *" in result.output


class TestScheduleRun:
    """Tests for 'filtarr schedule run' command."""

    def test_schedule_run_not_found(self) -> None:
        """Should exit 1 when schedule not found."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_schedule.return_value = None

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "run", "nonexistent"])

        assert result.exit_code == 1
        assert "Schedule not found" in result.output

    def test_schedule_run_success(self) -> None:
        """Should run schedule and display results."""
        schedule = _create_sample_schedule("test-schedule")
        run_record = _create_sample_run_record(
            "test-schedule",
            status=RunStatus.COMPLETED,
            items_processed=50,
            items_with_4k=10,
        )

        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_schedule.return_value = schedule

        async def mock_run_schedule(_name: str) -> ScheduleRunRecord:
            return run_record

        mock_manager.run_schedule = mock_run_schedule

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "run", "test-schedule"])

        assert result.exit_code == 0
        assert "Running schedule: test-schedule" in result.output
        assert "Result:" in result.output
        assert "completed" in result.output
        assert "Items processed: 50" in result.output
        assert "Items with 4K: 10" in result.output

    def test_schedule_run_with_errors(self) -> None:
        """Should display errors from schedule run."""
        schedule = _create_sample_schedule("test-schedule")
        run_record = ScheduleRunRecord(
            schedule_name="test-schedule",
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            completed_at=datetime.now(UTC),
            status=RunStatus.FAILED,
            items_processed=10,
            items_with_4k=0,
            errors=["Error 1", "Error 2", "Error 3"],
        )

        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_schedule.return_value = schedule

        async def mock_run_schedule(_name: str) -> ScheduleRunRecord:
            return run_record

        mock_manager.run_schedule = mock_run_schedule

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "run", "test-schedule"])

        assert result.exit_code == 0
        assert "failed" in result.output
        assert "Errors:" in result.output
        assert "Error 1" in result.output

    def test_schedule_run_displays_target(self) -> None:
        """Should display target type when running."""
        schedule = _create_sample_schedule("test-schedule", target=ScheduleTarget.BOTH)
        run_record = _create_sample_run_record("test-schedule")

        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_schedule.return_value = schedule

        async def mock_run_schedule(_name: str) -> ScheduleRunRecord:
            return run_record

        mock_manager.run_schedule = mock_run_schedule

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "run", "test-schedule"])

        assert result.exit_code == 0
        assert "Target: both" in result.output


class TestScheduleAdd:
    """Tests for 'filtarr schedule add' command."""

    def test_schedule_add_with_cron(self) -> None:
        """Should add schedule with cron trigger."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "daily-movies",
                    "--target",
                    "movies",
                    "--cron",
                    "0 3 * * *",
                ],
            )

        assert result.exit_code == 0
        assert "added successfully" in result.output
        mock_manager.add_schedule.assert_called_once()

    def test_schedule_add_with_interval(self) -> None:
        """Should add schedule with interval trigger."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "hourly-check",
                    "--target",
                    "both",
                    "--interval",
                    "6h",
                ],
            )

        assert result.exit_code == 0
        assert "added successfully" in result.output

    def test_schedule_add_no_trigger_error(self) -> None:
        """Should exit 2 when no trigger specified."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                ["schedule", "add", "test-schedule", "--target", "movies"],
            )

        assert result.exit_code == 2
        assert "Must specify --cron or --interval" in result.output

    def test_schedule_add_both_triggers_error(self) -> None:
        """Should exit 2 when both cron and interval specified."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "test-schedule",
                    "--cron",
                    "0 3 * * *",
                    "--interval",
                    "6h",
                ],
            )

        assert result.exit_code == 2
        assert "Cannot specify both --cron and --interval" in result.output

    def test_schedule_add_invalid_cron(self) -> None:
        """Should exit 2 for invalid cron expression."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "test-schedule",
                    "--cron",
                    "invalid-cron",
                ],
            )

        assert result.exit_code == 2
        assert "Invalid cron expression" in result.output

    def test_schedule_add_invalid_interval(self) -> None:
        """Should exit 2 for invalid interval format."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "test-schedule",
                    "--interval",
                    "invalid",
                ],
            )

        assert result.exit_code == 2
        assert "Invalid interval" in result.output

    def test_schedule_add_invalid_target(self) -> None:
        """Should exit 2 for invalid target."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "test-schedule",
                    "--target",
                    "invalid",
                    "--interval",
                    "6h",
                ],
            )

        assert result.exit_code == 2
        assert "Invalid target" in result.output

    def test_schedule_add_invalid_strategy(self) -> None:
        """Should exit 2 for invalid strategy."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "test-schedule",
                    "--interval",
                    "6h",
                    "--strategy",
                    "invalid",
                ],
            )

        assert result.exit_code == 2
        assert "Invalid strategy" in result.output

    def test_schedule_add_conflict_with_config(self) -> None:
        """Should exit 2 when name conflicts with config schedule."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.add_schedule.side_effect = ValueError(
            "schedule with this name is defined in config.toml"
        )

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "existing-schedule",
                    "--interval",
                    "6h",
                ],
            )

        assert result.exit_code == 2
        assert "config.toml" in result.output

    def test_schedule_add_with_all_options(self) -> None:
        """Should add schedule with all optional parameters."""
        mock_manager = _create_mock_scheduler_manager()

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "full-options",
                    "--target",
                    "series",
                    "--interval",
                    "1d",
                    "--batch-size",
                    "50",
                    "--delay",
                    "1.0",
                    "--no-skip-tagged",
                    "--strategy",
                    "distributed",
                    "--seasons",
                    "5",
                    "--disabled",
                ],
            )

        assert result.exit_code == 0
        mock_manager.add_schedule.assert_called_once()
        call_args = mock_manager.add_schedule.call_args[0][0]
        assert call_args.name == "full-options"
        assert call_args.batch_size == 50
        assert call_args.delay == 1.0
        assert call_args.skip_tagged is False
        assert call_args.enabled is False


class TestScheduleRemove:
    """Tests for 'filtarr schedule remove' command."""

    def test_schedule_remove_success(self) -> None:
        """Should remove schedule successfully."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.remove_schedule.return_value = True

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "remove", "test-schedule"])

        assert result.exit_code == 0
        assert "removed" in result.output

    def test_schedule_remove_not_found(self) -> None:
        """Should exit 1 when schedule not found."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.remove_schedule.return_value = False

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "remove", "nonexistent"])

        assert result.exit_code == 1
        assert "Schedule not found" in result.output

    def test_schedule_remove_config_schedule_error(self) -> None:
        """Should exit 2 when trying to remove config schedule."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.remove_schedule.side_effect = ValueError("it is defined in config.toml")

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "remove", "config-schedule"])

        assert result.exit_code == 2
        assert "config.toml" in result.output


class TestScheduleEnable:
    """Tests for 'filtarr schedule enable' command."""

    def test_schedule_enable_success(self) -> None:
        """Should enable schedule successfully."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.enable_schedule.return_value = True

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "enable", "test-schedule"])

        assert result.exit_code == 0
        assert "enabled" in result.output
        assert "Restart" in result.output

    def test_schedule_enable_not_found(self) -> None:
        """Should exit 1 when schedule not found."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.enable_schedule.return_value = False

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "enable", "nonexistent"])

        assert result.exit_code == 1
        assert "Schedule not found" in result.output

    def test_schedule_enable_config_schedule_error(self) -> None:
        """Should exit 2 when trying to enable config schedule."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.enable_schedule.side_effect = ValueError("it is defined in config.toml")

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "enable", "config-schedule"])

        assert result.exit_code == 2
        assert "config.toml" in result.output


class TestScheduleDisable:
    """Tests for 'filtarr schedule disable' command."""

    def test_schedule_disable_success(self) -> None:
        """Should disable schedule successfully."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.disable_schedule.return_value = True

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "disable", "test-schedule"])

        assert result.exit_code == 0
        assert "disabled" in result.output
        assert "Restart" in result.output

    def test_schedule_disable_not_found(self) -> None:
        """Should exit 1 when schedule not found."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.disable_schedule.return_value = False

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "disable", "nonexistent"])

        assert result.exit_code == 1
        assert "Schedule not found" in result.output

    def test_schedule_disable_config_schedule_error(self) -> None:
        """Should exit 2 when trying to disable config schedule."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.disable_schedule.side_effect = ValueError("it is defined in config.toml")

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "disable", "config-schedule"])

        assert result.exit_code == 2
        assert "config.toml" in result.output


class TestScheduleHistory:
    """Tests for 'filtarr schedule history' command."""

    def test_schedule_history_no_records(self) -> None:
        """Should show message when no history found."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = []

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history"])

        assert result.exit_code == 0
        assert "No history found" in result.output

    def test_schedule_history_with_records_table_format(self) -> None:
        """Should display history in table format."""
        records = [
            _create_sample_run_record("schedule-1", RunStatus.COMPLETED, 100, 25),
            _create_sample_run_record("schedule-2", RunStatus.FAILED, 50, 0),
        ]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = records

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history"])

        assert result.exit_code == 0
        assert "schedule-1" in result.output
        assert "schedule-2" in result.output
        assert "completed" in result.output
        assert "failed" in result.output

    def test_schedule_history_json_format(self) -> None:
        """Should display history in JSON format."""
        records = [_create_sample_run_record("test-schedule")]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = records

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["schedule_name"] == "test-schedule"

    def test_schedule_history_filter_by_name(self) -> None:
        """Should filter history by schedule name."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = []

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history", "--name", "specific-schedule"])

        mock_manager.get_history.assert_called_once_with(
            schedule_name="specific-schedule", limit=20
        )
        assert result.exit_code == 0

    def test_schedule_history_with_limit(self) -> None:
        """Should limit history records."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = []

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history", "--limit", "5"])

        mock_manager.get_history.assert_called_once_with(schedule_name=None, limit=5)
        assert result.exit_code == 0

    def test_schedule_history_duration_display(self) -> None:
        """Should display duration in human-readable format."""
        now = datetime.now(UTC)
        record = ScheduleRunRecord(
            schedule_name="test-schedule",
            started_at=now - timedelta(hours=1, minutes=30),
            completed_at=now,
            status=RunStatus.COMPLETED,
            items_processed=100,
            items_with_4k=25,
        )
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = [record]

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history"])

        assert result.exit_code == 0
        # Duration should be displayed (e.g., "1h 30m")
        assert "1h" in result.output or "90m" in result.output

    def test_schedule_history_running_status(self) -> None:
        """Should display running status correctly."""
        record = ScheduleRunRecord(
            schedule_name="test-schedule",
            started_at=datetime.now(UTC),
            completed_at=None,  # Still running
            status=RunStatus.RUNNING,
            items_processed=10,
            items_with_4k=2,
        )
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = [record]

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history"])

        assert result.exit_code == 0
        assert "running" in result.output

    def test_schedule_history_skipped_status(self) -> None:
        """Should display skipped status correctly."""
        now = datetime.now(UTC)
        record = ScheduleRunRecord(
            schedule_name="test-schedule",
            started_at=now,
            completed_at=now,
            status=RunStatus.SKIPPED,
            items_processed=0,
            items_with_4k=0,
        )
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_history.return_value = [record]

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "history"])

        assert result.exit_code == 0
        assert "skipped" in result.output


class TestScheduleExport:
    """Tests for 'filtarr schedule export' command."""

    def test_schedule_export_no_enabled_schedules(self) -> None:
        """Should show warning when no enabled schedules."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = [
            _create_sample_schedule("disabled-schedule", enabled=False)
        ]

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "export"])

        assert result.exit_code == 0
        assert "No enabled schedules to export" in result.output

    def test_schedule_export_cron_format(self) -> None:
        """Should export in cron format."""
        schedules = [_create_sample_schedule("daily-movies", enabled=True)]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "export", "--format", "cron"])

        assert result.exit_code == 0
        assert "daily-movies" in result.output
        assert "filtarr" in result.output
        assert "check batch" in result.output

    def test_schedule_export_systemd_format_stdout(self) -> None:
        """Should export systemd format to stdout."""
        schedules = [_create_sample_schedule("daily-movies", enabled=True)]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "export", "--format", "systemd"])

        assert result.exit_code == 0
        assert "filtarr-daily-movies.timer" in result.output
        assert "filtarr-daily-movies.service" in result.output
        assert "[Unit]" in result.output
        assert "[Timer]" in result.output
        assert "[Service]" in result.output

    def test_schedule_export_systemd_format_with_output_dir(self, tmp_path: Path) -> None:
        """Should write systemd files to output directory."""
        schedules = [_create_sample_schedule("daily-movies", enabled=True)]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                ["schedule", "export", "--format", "systemd", "--output", str(tmp_path)],
            )

        assert result.exit_code == 0
        assert "Generated" in result.output
        assert (tmp_path / "filtarr-daily-movies.timer").exists()
        assert (tmp_path / "filtarr-daily-movies.service").exists()

    def test_schedule_export_cron_format_with_output_file(self, tmp_path: Path) -> None:
        """Should write cron config to output file."""
        schedules = [_create_sample_schedule("daily-movies", enabled=True)]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        output_file = tmp_path / "filtarr.cron"

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                ["schedule", "export", "--format", "cron", "--output", str(output_file)],
            )

        assert result.exit_code == 0
        assert "written to" in result.output
        assert output_file.exists()
        content = output_file.read_text()
        assert "daily-movies" in content

    def test_schedule_export_invalid_format(self) -> None:
        """Should exit 2 for invalid format."""
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = [_create_sample_schedule("test-schedule")]

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "export", "--format", "invalid-format"])

        assert result.exit_code == 2
        assert "Invalid format" in result.output

    def test_schedule_export_multiple_schedules(self) -> None:
        """Should export multiple enabled schedules."""
        schedules = [
            _create_sample_schedule("schedule-1", enabled=True),
            _create_sample_schedule("schedule-2", enabled=True),
            _create_sample_schedule("schedule-3", enabled=False),
        ]
        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_all_schedules.return_value = schedules

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "export", "--format", "cron"])

        assert result.exit_code == 0
        assert "schedule-1" in result.output
        assert "schedule-2" in result.output
        assert "schedule-3" not in result.output


class TestScheduleHelpOutput:
    """Tests for schedule help output."""

    def test_schedule_help(self) -> None:
        """Should show schedule subcommand help."""
        result = runner.invoke(app, ["schedule", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "add" in result.output
        assert "remove" in result.output
        assert "enable" in result.output
        assert "disable" in result.output
        assert "run" in result.output
        assert "history" in result.output
        assert "export" in result.output

    def test_schedule_list_help(self) -> None:
        """Should show schedule list help."""
        result = runner.invoke(app, ["schedule", "list", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "--enabled-only" in output
        assert "--format" in output

    def test_schedule_add_help(self) -> None:
        """Should show schedule add help."""
        result = runner.invoke(app, ["schedule", "add", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "--target" in output
        assert "--cron" in output
        assert "--interval" in output
        assert "--batch-size" in output

    def test_schedule_run_help(self) -> None:
        """Should show schedule run help."""
        result = runner.invoke(app, ["schedule", "run", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "NAME" in output

    def test_schedule_history_help(self) -> None:
        """Should show schedule history help."""
        result = runner.invoke(app, ["schedule", "history", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "--name" in output
        assert "--limit" in output
        assert "--format" in output

    def test_schedule_export_help(self) -> None:
        """Should show schedule export help."""
        result = runner.invoke(app, ["schedule", "export", "--help"])
        output = _strip_ansi(result.output)
        assert result.exit_code == 0
        assert "--format" in output
        assert "--output" in output
        assert "cron" in output
        assert "systemd" in output


class TestGetSchedulerManager:
    """Tests for _get_scheduler_manager helper function."""

    def test_get_scheduler_manager_creates_manager(self) -> None:
        """Should create SchedulerManager with correct dependencies."""
        mock_config = _create_mock_config()
        mock_state_manager = _create_mock_state_manager()

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.scheduler.SchedulerManager") as mock_manager_class,
        ):
            from filtarr.cli import _get_scheduler_manager

            _get_scheduler_manager()
            mock_manager_class.assert_called_once_with(mock_config, mock_state_manager)
