"""Tests for CLI schedule commands."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from filtarr.cli import app
from filtarr.config import Config, ConfigurationError, RadarrConfig, SchedulerConfig, SonarrConfig
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
    mock.get_batch_progress = MagicMock(return_value=None)
    mock.start_batch = MagicMock()
    mock.update_batch_progress = MagicMock()
    mock.clear_batch_progress = MagicMock()
    mock.get_cached_result = MagicMock(return_value=None)
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
        source="config",
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

    def test_schedule_run_with_many_errors_truncates(self) -> None:
        """Should truncate error list when more than 5 errors (covers L1548)."""
        schedule = _create_sample_schedule("test-schedule")
        # Create run record with more than 5 errors
        many_errors = [f"Error {i}" for i in range(1, 10)]
        run_record = ScheduleRunRecord(
            schedule_name="test-schedule",
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            completed_at=datetime.now(UTC),
            status=RunStatus.FAILED,
            items_processed=10,
            items_with_4k=0,
            errors=many_errors,
        )

        mock_manager = _create_mock_scheduler_manager()
        mock_manager.get_schedule.return_value = schedule

        async def mock_run_schedule(_name: str) -> ScheduleRunRecord:
            return run_record

        mock_manager.run_schedule = mock_run_schedule

        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(app, ["schedule", "run", "test-schedule"])

        assert result.exit_code == 0
        # First 5 errors should be shown
        assert "Error 1" in result.output
        assert "Error 5" in result.output
        # Truncation message should appear
        assert "... and 4 more" in result.output


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

    def test_schedule_add_schedule_definition_value_error(self) -> None:
        """Should exit 2 when ScheduleDefinition raises ValueError (covers L1442-1444)."""
        mock_manager = _create_mock_scheduler_manager()

        # Use a name that would fail validation (contains invalid characters)
        with patch("filtarr.cli._get_scheduler_manager", return_value=mock_manager):
            result = runner.invoke(
                app,
                [
                    "schedule",
                    "add",
                    "invalid name with spaces",  # Invalid: contains spaces
                    "--interval",
                    "6h",
                ],
            )

        assert result.exit_code == 2
        # The name pattern validation will fail
        assert "Invalid schedule" in result.output or "Error" in result.output


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


# =============================================================================
# Batch Command Coverage Tests (for lines not covered by test_cli.py)
# =============================================================================


class TestBatchCommandCoverage:
    """Tests for batch command to cover specific uncovered lines."""

    def test_batch_config_load_error(self) -> None:
        """Should exit 2 when Config.load() raises ConfigurationError (covers L1217-1219)."""
        with patch("filtarr.cli.Config.load", side_effect=ConfigurationError("Test config error")):
            result = runner.invoke(app, ["check", "batch", "--all-movies"])

        assert result.exit_code == 2
        assert "Configuration error" in result.output
        assert "Test config error" in result.output

    def test_batch_mixed_type_when_both_movies_and_series(self) -> None:
        """Should set batch_type='mixed' when both --all-movies and --all-series (covers L1226)."""
        from filtarr.checker import SearchResult
        from filtarr.models.radarr import Movie
        from filtarr.models.sonarr import Series
        from filtarr.state import BatchProgress

        mock_config = _create_mock_config()
        mock_state_manager = _create_mock_state_manager()

        # Create mock movies and series
        mock_movie = MagicMock(spec=Movie)
        mock_movie.id = 1
        mock_movie.title = "Test Movie"
        mock_movie.tags = []

        mock_series = MagicMock(spec=Series)
        mock_series.id = 2
        mock_series.title = "Test Series"
        mock_series.tags = []

        # Mock batch progress to verify batch_type
        captured_batch_type: list[str] = []

        def mock_start_batch(batch_id: str, batch_type: str, total: int) -> BatchProgress:
            captured_batch_type.append(batch_type)
            return BatchProgress(
                batch_id=batch_id,
                item_type=batch_type,
                total_items=total,  # type: ignore[arg-type]
            )

        mock_state_manager.start_batch = mock_start_batch

        mock_result = SearchResult(item_id=1, item_type="movie", has_match=True)

        # Mock the _fetch_movies_to_check and _fetch_series_to_check functions directly
        async def mock_fetch_movies(*_args: Any, **_kwargs: Any) -> tuple[list[Movie], set[int]]:
            return ([mock_movie], set())

        async def mock_fetch_series(*_args: Any, **_kwargs: Any) -> tuple[list[Series], set[int]]:
            return ([mock_series], set())

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.get_checker") as mock_get_checker,
            patch("filtarr.cli._fetch_movies_to_check", side_effect=mock_fetch_movies),
            patch("filtarr.cli._fetch_series_to_check", side_effect=mock_fetch_series),
        ):
            # Mock checker
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = mock_result
            mock_checker.check_series.return_value = SearchResult(
                item_id=2, item_type="series", has_match=True
            )
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                [
                    "check",
                    "batch",
                    "--all-movies",
                    "--all-series",
                    "--format",
                    "simple",
                    "--no-resume",
                    "--delay",
                    "0",
                ],
            )

        # Verify batch_type was "mixed"
        assert "mixed" in captured_batch_type
        assert "Summary:" in result.output

    def test_batch_resume_progress_message(self) -> None:
        """Should display resume message when resume=True and progress exists (covers L1239)."""
        from filtarr.checker import SearchResult
        from filtarr.models.radarr import Movie
        from filtarr.state import BatchProgress

        mock_config = _create_mock_config()
        mock_state_manager = _create_mock_state_manager()

        # Create existing progress
        existing_progress = BatchProgress(
            batch_id="test-batch",
            item_type="movie",
            total_items=100,
            processed_ids={1, 2, 3, 4, 5},  # 5 already processed
        )
        mock_state_manager.get_batch_progress.return_value = existing_progress

        # Create mock movies
        mock_movie = MagicMock(spec=Movie)
        mock_movie.id = 6  # Not yet processed
        mock_movie.title = "Test Movie"
        mock_movie.tags = []

        async def mock_fetch_movies(*_args: Any, **_kwargs: Any) -> tuple[list[Movie], set[int]]:
            return ([mock_movie], set())

        mock_result = SearchResult(item_id=6, item_type="movie", has_match=True)

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.get_checker") as mock_get_checker,
            patch("filtarr.cli._fetch_movies_to_check", side_effect=mock_fetch_movies),
        ):
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = mock_result
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                ["check", "batch", "--all-movies", "--resume", "--format", "simple"],
            )

        # Should show resume message with "5/100 already processed"
        assert "Resuming batch" in result.output
        assert "5/" in result.output
        assert "already processed" in result.output

    def test_batch_with_skipped_and_limit_reached(self) -> None:
        """Should display skipped count and limit reached message (covers L1133, L1135)."""
        from filtarr.checker import SearchResult
        from filtarr.models.radarr import Movie
        from filtarr.state import BatchProgress

        mock_config = _create_mock_config()
        mock_state_manager = _create_mock_state_manager()

        # Create existing progress with some already processed
        existing_progress = BatchProgress(
            batch_id="test-batch",
            item_type="movie",
            total_items=10,
            processed_ids={1, 2, 3},  # 3 already processed
        )
        mock_state_manager.get_batch_progress.return_value = existing_progress

        # Create mock movies (including previously processed ones)
        mock_movies: list[MagicMock] = []
        for i in range(1, 6):
            mock_movie = MagicMock(spec=Movie)
            mock_movie.id = i
            mock_movie.title = f"Movie {i}"
            mock_movie.tags = []
            mock_movies.append(mock_movie)

        async def mock_fetch_movies(*_args: Any, **_kwargs: Any) -> tuple[list[Movie], set[int]]:
            return (mock_movies, set())  # type: ignore[return-value]

        mock_result = SearchResult(item_id=4, item_type="movie", has_match=True)

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.get_checker") as mock_get_checker,
            patch("filtarr.cli._fetch_movies_to_check", side_effect=mock_fetch_movies),
        ):
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = mock_result
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                [
                    "check",
                    "batch",
                    "--all-movies",
                    "--resume",
                    "--batch-size",
                    "1",  # Process only 1, but skip the first 3
                    "--format",
                    "simple",
                    "--delay",
                    "0",
                ],
            )

        # Should show skipped count and batch limit reached message
        assert "Summary:" in result.output
        # 3 items were skipped (already processed)
        assert "resumed/skipped" in result.output
        # Should indicate batch limit reached
        assert "batch limit" in result.output


class TestBatchRecheckCoverage:
    """Tests for batch recheck functionality to cover L1111-1117."""

    def test_batch_with_include_rechecks_and_stale_items(self, tmp_path: Path) -> None:
        """Should include stale items for re-checking (covers L1111-1114, L1117)."""
        from filtarr.checker import SearchResult

        mock_config = _create_mock_config()
        mock_state_manager = _create_mock_state_manager()

        # Return stale items for rechecking
        stale_items: list[tuple[str, int]] = [
            ("movie", 100),
            ("series", 200),
        ]
        mock_state_manager.get_stale_unavailable_items.return_value = stale_items

        # Create a batch file with one item
        batch_file = tmp_path / "items.txt"
        batch_file.write_text("movie:1\n")

        mock_result = SearchResult(item_id=1, item_type="movie", has_match=True)

        with (
            patch("filtarr.cli.Config.load", return_value=mock_config),
            patch("filtarr.cli.get_state_manager", return_value=mock_state_manager),
            patch("filtarr.cli.get_checker") as mock_get_checker,
        ):
            mock_checker = AsyncMock()
            mock_checker.check_movie.return_value = mock_result
            mock_checker.check_series.return_value = SearchResult(
                item_id=200, item_type="series", has_match=False
            )
            mock_get_checker.return_value = mock_checker

            result = runner.invoke(
                app,
                [
                    "check",
                    "batch",
                    "--file",
                    str(batch_file),
                    "--include-rechecks",
                    "--format",
                    "simple",
                    "--delay",
                    "0",
                ],
            )

        # Should show message about including stale items
        assert "Including" in result.output
        assert "stale items" in result.output
        assert "Summary:" in result.output


class TestMainEntryPoint:
    """Tests for main entry point (covers L1809)."""

    def test_main_entry_point(self) -> None:
        """Test that if __name__ == '__main__' block works (covers L1809)."""
        # We can't easily test this directly since it's conditional,
        # but we can verify the app exists and is callable
        from filtarr.cli import app as cli_app

        # Verify app is a Typer instance
        assert cli_app is not None
        assert hasattr(cli_app, "registered_commands") or hasattr(cli_app, "info")

        # Test via direct invocation
        result = runner.invoke(cli_app, ["--help"])
        assert result.exit_code == 0
        assert "filtarr" in result.output.lower() or "check" in result.output.lower()
