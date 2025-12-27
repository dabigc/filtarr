"""Tests for the SchedulerManager class."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from filtarr.config import Config, RadarrConfig, SchedulerConfig, SonarrConfig, TagConfig
from filtarr.scheduler import (
    IntervalTrigger,
    RunStatus,
    ScheduleDefinition,
    ScheduleRunRecord,
    ScheduleTarget,
)
from filtarr.scheduler.manager import SchedulerManager, _to_float, _to_int
from filtarr.state import StateManager

if TYPE_CHECKING:
    from pathlib import Path


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_config() -> Config:
    """Create a mock config for testing."""
    return Config(
        radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-key"),
        sonarr=SonarrConfig(url="http://127.0.0.1:8989", api_key="sonarr-key"),
        timeout=30.0,
        tags=TagConfig(),
        scheduler=SchedulerConfig(enabled=True, history_limit=100, schedules=[]),
    )


@pytest.fixture
def mock_state_manager(tmp_path: Path) -> StateManager:
    """Create a mock state manager for testing."""
    state_path = tmp_path / "state.json"
    return StateManager(state_path)


@pytest.fixture
def config_with_schedule() -> Config:
    """Create a config with a schedule defined."""
    return Config(
        radarr=RadarrConfig(url="http://localhost:7878", api_key="radarr-key"),
        scheduler=SchedulerConfig(
            enabled=True,
            schedules=[
                {
                    "name": "config-schedule",
                    "target": "movies",
                    "trigger": {"type": "interval", "hours": 6},
                    "enabled": True,
                }
            ],
        ),
    )


# ============================================================================
# Tests for helper functions (_to_int, _to_float)
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions _to_int and _to_float."""

    def test_to_int_with_valid_string(self) -> None:
        """Test _to_int with a valid string number."""
        assert _to_int("42") == 42

    def test_to_int_with_invalid_string_returns_default(self) -> None:
        """Test _to_int with an invalid string returns the default value."""
        assert _to_int("not_a_number", 42) == 42

    def test_to_int_with_empty_string_returns_default(self) -> None:
        """Test _to_int with an empty string returns the default value."""
        assert _to_int("", 99) == 99

    def test_to_int_with_float_string_returns_default(self) -> None:
        """Test _to_int with a float string returns the default value."""
        # "3.14" cannot be converted to int directly
        assert _to_int("3.14", 10) == 10

    def test_to_int_with_list_returns_default(self) -> None:
        """Test _to_int with a list returns the default value."""
        # Lists are not SupportsInt and not strings, so they fall through to the final return
        assert _to_int([1, 2, 3], 77) == 77

    def test_to_int_with_dict_returns_default(self) -> None:
        """Test _to_int with a dict returns the default value."""
        # Dicts are not SupportsInt and not strings, so they fall through to the final return
        assert _to_int({"key": "value"}, 88) == 88

    def test_to_int_with_object_returns_default(self) -> None:
        """Test _to_int with a custom object without __int__ returns the default value."""

        class NoIntMethod:
            pass

        assert _to_int(NoIntMethod(), 55) == 55

    def test_to_float_with_valid_string(self) -> None:
        """Test _to_float with a valid string number."""
        assert _to_float("3.14") == 3.14

    def test_to_float_with_invalid_string_returns_default(self) -> None:
        """Test _to_float with an invalid string returns the default value."""
        assert _to_float("not_a_float", 3.14) == 3.14

    def test_to_float_with_empty_string_returns_default(self) -> None:
        """Test _to_float with an empty string returns the default value."""
        assert _to_float("", 1.5) == 1.5

    def test_to_float_with_special_chars_returns_default(self) -> None:
        """Test _to_float with special characters returns the default value."""
        assert _to_float("abc!@#", 2.5) == 2.5

    def test_to_float_with_list_returns_default(self) -> None:
        """Test _to_float with a list returns the default value."""
        # Lists are not SupportsFloat and not strings, so they fall through to the final return
        assert _to_float([1.0, 2.0], 7.7) == 7.7

    def test_to_float_with_dict_returns_default(self) -> None:
        """Test _to_float with a dict returns the default value."""
        # Dicts are not SupportsFloat and not strings, so they fall through to the final return
        assert _to_float({"key": 1.5}, 8.8) == 8.8

    def test_to_float_with_object_returns_default(self) -> None:
        """Test _to_float with a custom object without __float__ returns the default value."""

        class NoFloatMethod:
            pass

        assert _to_float(NoFloatMethod(), 5.5) == 5.5


# ============================================================================
# Tests for get_all_schedules() with malformed data
# ============================================================================


class TestGetAllSchedulesMalformedData:
    """Tests for get_all_schedules() handling of malformed schedule data."""

    def test_config_schedule_with_non_dict_trigger_is_skipped(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test that config schedules with non-dict trigger data are skipped."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "valid-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    },
                    {
                        "name": "invalid-trigger-string",
                        "target": "movies",
                        "trigger": "not-a-dict",  # Invalid: string instead of dict
                    },
                    {
                        "name": "invalid-trigger-list",
                        "target": "movies",
                        "trigger": ["interval", 6],  # Invalid: list instead of dict
                    },
                    {
                        "name": "invalid-trigger-none",
                        "target": "movies",
                        "trigger": None,  # Invalid: None instead of dict
                    },
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)
        schedules = manager.get_all_schedules()

        # Only the valid schedule should be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-schedule"

    def test_config_schedule_with_invalid_trigger_type_logs_error(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test that config schedules with invalid trigger type log an error and continue."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "invalid-trigger-type",
                        "target": "movies",
                        "trigger": {"type": "unknown_trigger_type"},  # Invalid type
                    },
                    {
                        "name": "valid-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    },
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        with patch("filtarr.scheduler.manager.logger") as mock_logger:
            schedules = manager.get_all_schedules()

            # Should log error for invalid trigger type
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args
            assert "Failed to parse config schedule" in error_call[0][0]
            assert "invalid-trigger-type" in str(error_call)

        # Valid schedule should still be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-schedule"

    def test_dynamic_schedule_with_non_dict_trigger_is_skipped(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that dynamic schedules with non-dict trigger data are skipped."""
        # Add dynamic schedules with malformed trigger data directly to state
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "valid-dynamic",
                "target": "movies",
                "trigger": {"type": "interval", "hours": 12},
            }
        )
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "invalid-dynamic-string-trigger",
                "target": "movies",
                "trigger": "not-a-dict",  # Invalid: string instead of dict
            }
        )
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "invalid-dynamic-list-trigger",
                "target": "series",
                "trigger": [1, 2, 3],  # Invalid: list instead of dict
            }
        )
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "invalid-dynamic-int-trigger",
                "target": "both",
                "trigger": 12345,  # Invalid: int instead of dict
            }
        )

        manager = SchedulerManager(mock_config, mock_state_manager)
        schedules = manager.get_all_schedules()

        # Only the valid dynamic schedule should be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-dynamic"
        assert schedules[0].source == "dynamic"

    def test_dynamic_schedule_with_invalid_trigger_type_logs_error(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that dynamic schedules with invalid trigger type log an error and continue."""
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "invalid-type-dynamic",
                "target": "movies",
                "trigger": {"type": "foobar_invalid"},  # Invalid trigger type
            }
        )
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "valid-dynamic",
                "target": "movies",
                "trigger": {"type": "interval", "hours": 6},
            }
        )

        manager = SchedulerManager(mock_config, mock_state_manager)

        with patch("filtarr.scheduler.manager.logger") as mock_logger:
            schedules = manager.get_all_schedules()

            # Should log error for invalid trigger type
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args
            assert "Failed to parse dynamic schedule" in error_call[0][0]
            assert "invalid-type-dynamic" in str(error_call)

        # Valid schedule should still be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-dynamic"

    def test_config_schedule_missing_trigger_field_uses_empty_dict(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test that config schedule with missing trigger field gets empty dict and fails."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "no-trigger",
                        "target": "movies",
                        # No "trigger" key at all
                    },
                    {
                        "name": "valid-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    },
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        with patch("filtarr.scheduler.manager.logger") as mock_logger:
            schedules = manager.get_all_schedules()

            # Missing trigger causes parse_trigger to fail (empty dict has no 'type')
            # Should log error for missing trigger
            mock_logger.error.assert_called()

        # Only valid schedule should be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-schedule"

    def test_dynamic_schedule_missing_trigger_field_uses_empty_dict(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that dynamic schedule with missing trigger field gets empty dict and fails."""
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "no-trigger-dynamic",
                "target": "movies",
                # No "trigger" key at all
            }
        )
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "valid-dynamic",
                "target": "movies",
                "trigger": {"type": "interval", "hours": 6},
            }
        )

        manager = SchedulerManager(mock_config, mock_state_manager)

        with patch("filtarr.scheduler.manager.logger") as mock_logger:
            schedules = manager.get_all_schedules()

            # Missing trigger causes parse_trigger to fail
            mock_logger.error.assert_called()

        # Only valid schedule should be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-dynamic"

    def test_config_schedule_exception_during_schedule_definition_creation(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test that exceptions during ScheduleDefinition creation are caught and logged."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "schedule-with-bad-name!!!",  # Invalid chars in name
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    },
                    {
                        "name": "valid-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    },
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        with patch("filtarr.scheduler.manager.logger") as mock_logger:
            schedules = manager.get_all_schedules()

            # Should log error for invalid schedule name
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args
            assert "Failed to parse config schedule" in error_call[0][0]

        # Only valid schedule should be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-schedule"

    def test_dynamic_schedule_exception_during_schedule_definition_creation(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that exceptions during dynamic ScheduleDefinition creation are caught."""
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "bad-name-chars@#$",  # Invalid chars in name
                "target": "movies",
                "trigger": {"type": "interval", "hours": 6},
            }
        )
        mock_state_manager.add_dynamic_schedule(
            {
                "name": "valid-dynamic",
                "target": "movies",
                "trigger": {"type": "interval", "hours": 6},
            }
        )

        manager = SchedulerManager(mock_config, mock_state_manager)

        with patch("filtarr.scheduler.manager.logger") as mock_logger:
            schedules = manager.get_all_schedules()

            # Should log error for invalid schedule name
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args
            assert "Failed to parse dynamic schedule" in error_call[0][0]

        # Only valid schedule should be returned
        assert len(schedules) == 1
        assert schedules[0].name == "valid-dynamic"


# ============================================================================
# Tests for start() method
# ============================================================================


class TestSchedulerManagerStart:
    """Tests for SchedulerManager.start() method."""

    @pytest.mark.asyncio
    async def test_start_with_enabled_schedules(self, mock_state_manager: StateManager) -> None:
        """Test starting scheduler with enabled schedules."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "test-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                        "enabled": True,
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        # Mock APScheduler - patch the import inside start()
        mock_scheduler = AsyncMock()
        mock_scheduler.add_schedule = AsyncMock()
        mock_scheduler.start_in_background = AsyncMock()

        mock_apscheduler_module = MagicMock()
        mock_apscheduler_module.AsyncScheduler = MagicMock(return_value=mock_scheduler)

        # Also mock apscheduler triggers submodule
        mock_interval_trigger = MagicMock()
        mock_triggers_interval = MagicMock()
        mock_triggers_interval.IntervalTrigger = MagicMock(return_value=mock_interval_trigger)
        mock_triggers_cron = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "apscheduler": mock_apscheduler_module,
                "apscheduler.triggers": MagicMock(),
                "apscheduler.triggers.interval": mock_triggers_interval,
                "apscheduler.triggers.cron": mock_triggers_cron,
            },
        ):
            await manager.start()

        assert manager.is_running is True
        assert manager._started is True
        assert manager._scheduler is mock_scheduler
        mock_scheduler.add_schedule.assert_called_once()
        mock_scheduler.start_in_background.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_already_started_logs_warning(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test that starting an already started scheduler logs warning."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "test",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)
        manager._started = True

        # Should return early without creating new scheduler
        await manager.start()

        # Scheduler should not be set since we returned early
        assert manager._scheduler is None

    @pytest.mark.asyncio
    async def test_start_apscheduler_not_installed(self, mock_state_manager: StateManager) -> None:
        """Test start when APScheduler is not installed."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "test",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        # Remove apscheduler from sys.modules to simulate it not being installed
        # and make import raise ImportError
        import sys

        original_modules = sys.modules.copy()

        # Remove apscheduler and related modules
        modules_to_remove = [k for k in sys.modules if k.startswith("apscheduler")]
        for mod in modules_to_remove:
            sys.modules.pop(mod, None)

        # Create a mock that raises ImportError
        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals: dict[str, Any] | None = None,
            locals: dict[str, Any] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if name == "apscheduler" or name.startswith("apscheduler."):
                raise ImportError("No module named 'apscheduler'")
            return original_import(name, globals, locals, fromlist, level)

        try:
            builtins.__import__ = mock_import  # type: ignore[assignment]
            await manager.start()
        finally:
            builtins.__import__ = original_import
            # Restore original modules
            sys.modules.update(original_modules)

        assert manager.is_running is False
        assert manager._started is False

    @pytest.mark.asyncio
    async def test_start_no_enabled_schedules(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that start returns early with no enabled schedules."""
        # mock_config has no schedules defined
        manager = SchedulerManager(mock_config, mock_state_manager)

        await manager.start()

        assert manager.is_running is False
        assert manager._started is False
        assert manager._scheduler is None

    @pytest.mark.asyncio
    async def test_start_with_disabled_schedules_only(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test start when all schedules are disabled."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "disabled-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                        "enabled": False,
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        await manager.start()

        assert manager.is_running is False
        assert manager._started is False

    @pytest.mark.asyncio
    async def test_start_handles_add_schedule_error(self, mock_state_manager: StateManager) -> None:
        """Test that start handles errors when adding individual schedules."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "failing-schedule",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                        "enabled": True,
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        mock_scheduler = AsyncMock()
        mock_scheduler.add_schedule = AsyncMock(side_effect=Exception("Failed to add schedule"))
        mock_scheduler.start_in_background = AsyncMock()

        mock_apscheduler_module = MagicMock()
        mock_apscheduler_module.AsyncScheduler = MagicMock(return_value=mock_scheduler)

        with patch.dict("sys.modules", {"apscheduler": mock_apscheduler_module}):
            await manager.start()

        # Should still mark as started even if individual schedules fail
        assert manager._started is True
        mock_scheduler.start_in_background.assert_called_once()


# ============================================================================
# Tests for stop() method
# ============================================================================


class TestSchedulerManagerStop:
    """Tests for SchedulerManager.stop() method."""

    @pytest.mark.asyncio
    async def test_stop_normal(self, mock_state_manager: StateManager) -> None:
        """Test normal stop operation."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(enabled=True, schedules=[]),
        )

        manager = SchedulerManager(config, mock_state_manager)

        # Set up as if scheduler was started
        mock_scheduler = AsyncMock()
        mock_scheduler.stop = AsyncMock()
        manager._scheduler = mock_scheduler
        manager._started = True

        await manager.stop()

        mock_scheduler.stop.assert_called_once()
        assert manager._scheduler is None
        assert manager._started is False
        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_stop_with_running_jobs_wait_true(self, mock_state_manager: StateManager) -> None:
        """Test stop with running jobs and wait=True."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(enabled=True, schedules=[]),
        )

        manager = SchedulerManager(config, mock_state_manager)

        mock_scheduler = AsyncMock()
        mock_scheduler.stop = AsyncMock()
        manager._scheduler = mock_scheduler
        manager._started = True
        manager._running_jobs.add("test-job")

        # Simulate job completing after a short delay
        async def clear_jobs() -> None:
            await asyncio.sleep(0.1)
            manager._running_jobs.clear()

        task = asyncio.create_task(clear_jobs())

        await manager.stop(wait=True)

        # Ensure the background task completes
        await task

        mock_scheduler.stop.assert_called_once()
        assert manager._scheduler is None
        assert manager._started is False

    @pytest.mark.asyncio
    async def test_stop_with_running_jobs_wait_false(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test stop with running jobs and wait=False."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(enabled=True, schedules=[]),
        )

        manager = SchedulerManager(config, mock_state_manager)

        mock_scheduler = AsyncMock()
        mock_scheduler.stop = AsyncMock()
        manager._scheduler = mock_scheduler
        manager._started = True
        manager._running_jobs.add("test-job")

        # Should not wait for jobs to complete
        await manager.stop(wait=False)

        mock_scheduler.stop.assert_called_once()
        assert manager._scheduler is None
        assert manager._started is False

    @pytest.mark.asyncio
    async def test_stop_when_not_started(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that stop is safe when scheduler is not started."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Should not raise any errors
        await manager.stop()

        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_stop_when_scheduler_is_none(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test stop when _scheduler is None but _started is True."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        manager._started = True
        manager._scheduler = None

        # Should return early without error
        await manager.stop()


# ============================================================================
# Tests for enable_schedule() / disable_schedule()
# ============================================================================


class TestSchedulerManagerEnableDisable:
    """Tests for enable_schedule and disable_schedule methods."""

    def test_enable_schedule_dynamic_exists(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test enabling a dynamic schedule that exists."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Add a disabled dynamic schedule
        schedule = ScheduleDefinition(
            name="dynamic-test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            enabled=False,
        )
        manager.add_schedule(schedule)

        # Enable it
        result = manager.enable_schedule("dynamic-test")

        assert result is True

    def test_enable_schedule_not_found(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test enabling a schedule that doesn't exist returns False."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        result = manager.enable_schedule("nonexistent")

        assert result is False

    def test_enable_schedule_config_raises_valueerror(
        self, config_with_schedule: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that enabling a config schedule raises ValueError."""
        manager = SchedulerManager(config_with_schedule, mock_state_manager)

        with pytest.raises(ValueError, match=r"defined in config\.toml"):
            manager.enable_schedule("config-schedule")

    def test_disable_schedule_dynamic_exists(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test disabling a dynamic schedule that exists."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Add an enabled dynamic schedule
        schedule = ScheduleDefinition(
            name="dynamic-test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
            enabled=True,
        )
        manager.add_schedule(schedule)

        # Disable it
        result = manager.disable_schedule("dynamic-test")

        assert result is True

    def test_disable_schedule_not_found(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test disabling a schedule that doesn't exist returns False."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        result = manager.disable_schedule("nonexistent")

        assert result is False

    def test_disable_schedule_config_raises_valueerror(
        self, config_with_schedule: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that disabling a config schedule raises ValueError."""
        manager = SchedulerManager(config_with_schedule, mock_state_manager)

        with pytest.raises(ValueError, match=r"defined in config\.toml"):
            manager.disable_schedule("config-schedule")

    def test_enable_schedule_case_insensitive(
        self, config_with_schedule: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that schedule name matching is case insensitive."""
        manager = SchedulerManager(config_with_schedule, mock_state_manager)

        # Should raise even with different case
        with pytest.raises(ValueError, match=r"defined in config\.toml"):
            manager.enable_schedule("CONFIG-SCHEDULE")

    def test_disable_schedule_case_insensitive(
        self, config_with_schedule: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that schedule name matching is case insensitive for disable."""
        manager = SchedulerManager(config_with_schedule, mock_state_manager)

        # Should raise even with different case
        with pytest.raises(ValueError, match=r"defined in config\.toml"):
            manager.disable_schedule("Config-Schedule")


# ============================================================================
# Tests for _execute_schedule()
# ============================================================================


class TestSchedulerManagerExecuteSchedule:
    """Tests for _execute_schedule method with overlap protection."""

    @pytest.mark.asyncio
    async def test_execute_schedule_overlap_protection(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that overlapping schedule runs are skipped."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        schedule = ScheduleDefinition(
            name="overlap-test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )

        # Simulate a running job
        manager._running_jobs.add("overlap-test")

        result = await manager._execute_schedule(schedule)

        assert result.status == RunStatus.SKIPPED
        assert result.schedule_name == "overlap-test"

    @pytest.mark.asyncio
    async def test_execute_schedule_overlap_records_run(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that skipped runs are recorded in state."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        schedule = ScheduleDefinition(
            name="overlap-test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )

        # Simulate a running job
        manager._running_jobs.add("overlap-test")

        await manager._execute_schedule(schedule)

        # Verify run was recorded
        history = manager.get_history(schedule_name="overlap-test")
        assert len(history) == 1
        assert history[0].status == RunStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_execute_schedule_normal_execution(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test normal execution adds and removes from running jobs."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        schedule = ScheduleDefinition(
            name="normal-test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )

        mock_result = ScheduleRunRecord(
            schedule_name="normal-test",
            started_at=datetime.now(UTC),
            status=RunStatus.COMPLETED,
            items_processed=10,
            items_with_4k=5,
        )

        with patch.object(manager._executor, "execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result

            # Verify job is not in running set before
            assert "normal-test" not in manager._running_jobs

            result = await manager._execute_schedule(schedule)

            # Verify job is removed from running set after
            assert "normal-test" not in manager._running_jobs
            assert result.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_schedule_removes_from_running_on_exception(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that job is removed from running set even on exception."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        schedule = ScheduleDefinition(
            name="exception-test",
            target=ScheduleTarget.MOVIES,
            trigger=IntervalTrigger(hours=6),
        )

        with patch.object(manager._executor, "execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Executor failed")

            with pytest.raises(Exception, match="Executor failed"):
                await manager._execute_schedule(schedule)

            # Job should be removed from running set
            assert "exception-test" not in manager._running_jobs


# ============================================================================
# Tests for _job_callback()
# ============================================================================


class TestSchedulerManagerJobCallback:
    """Tests for _job_callback method."""

    @pytest.mark.asyncio
    async def test_job_callback_schedule_not_found(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that job callback handles missing schedule gracefully."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        # Should not raise, just return early
        await manager._job_callback("nonexistent-schedule")

    @pytest.mark.asyncio
    async def test_job_callback_executes_schedule(self, mock_state_manager: StateManager) -> None:
        """Test that job callback executes the found schedule."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "callback-test",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        mock_result = ScheduleRunRecord(
            schedule_name="callback-test",
            started_at=datetime.now(UTC),
            status=RunStatus.COMPLETED,
        )

        with patch.object(manager, "_execute_schedule", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result

            await manager._job_callback("callback-test")

            mock_execute.assert_called_once()
            # Verify the schedule passed to _execute_schedule
            call_args = mock_execute.call_args[0][0]
            assert call_args.name == "callback-test"

    @pytest.mark.asyncio
    async def test_job_callback_logs_error_for_missing_schedule(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that job callback logs error when schedule not found."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        with patch("filtarr.scheduler.manager.logger") as mock_logger:
            await manager._job_callback("missing-schedule")

            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args[0]
            assert "Schedule not found" in call_args[0]
            assert "missing-schedule" in call_args[1]


# ============================================================================
# Tests for run_schedule()
# ============================================================================


class TestSchedulerManagerRunSchedule:
    """Tests for run_schedule method."""

    @pytest.mark.asyncio
    async def test_run_schedule_not_found_raises_valueerror(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that running a non-existent schedule raises ValueError."""
        manager = SchedulerManager(mock_config, mock_state_manager)

        with pytest.raises(ValueError, match="Schedule not found"):
            await manager.run_schedule("nonexistent")

    @pytest.mark.asyncio
    async def test_run_schedule_executes_and_returns_record(
        self, mock_state_manager: StateManager
    ) -> None:
        """Test that run_schedule executes and returns a record."""
        config = Config(
            radarr=RadarrConfig(url="http://localhost:7878", api_key="key"),
            scheduler=SchedulerConfig(
                enabled=True,
                schedules=[
                    {
                        "name": "run-test",
                        "target": "movies",
                        "trigger": {"type": "interval", "hours": 6},
                    }
                ],
            ),
        )

        manager = SchedulerManager(config, mock_state_manager)

        mock_result = ScheduleRunRecord(
            schedule_name="run-test",
            started_at=datetime.now(UTC),
            status=RunStatus.COMPLETED,
            items_processed=5,
        )

        with patch.object(manager, "_execute_schedule", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result

            result = await manager.run_schedule("run-test")

            assert result.status == RunStatus.COMPLETED
            assert result.items_processed == 5


# ============================================================================
# Tests for is_running property
# ============================================================================


class TestSchedulerManagerIsRunning:
    """Tests for is_running property."""

    def test_is_running_false_initially(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that is_running is False initially."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        assert manager.is_running is False

    def test_is_running_false_when_started_but_no_scheduler(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test is_running is False when _started is True but _scheduler is None."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        manager._started = True
        manager._scheduler = None
        assert manager.is_running is False

    def test_is_running_false_when_scheduler_but_not_started(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test is_running is False when _scheduler exists but _started is False."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        manager._started = False
        manager._scheduler = MagicMock()
        assert manager.is_running is False

    def test_is_running_true_when_both_conditions_met(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test is_running is True when _started and _scheduler both set."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        manager._started = True
        manager._scheduler = MagicMock()
        assert manager.is_running is True


# ============================================================================
# Tests for get_running_schedules()
# ============================================================================


class TestSchedulerManagerGetRunningSchedules:
    """Tests for get_running_schedules method."""

    def test_get_running_schedules_returns_copy(
        self, mock_config: Config, mock_state_manager: StateManager
    ) -> None:
        """Test that get_running_schedules returns a copy of the set."""
        manager = SchedulerManager(mock_config, mock_state_manager)
        manager._running_jobs.add("job-1")
        manager._running_jobs.add("job-2")

        running = manager.get_running_schedules()

        # Verify it's a copy
        running.add("job-3")
        assert "job-3" not in manager._running_jobs

        # Verify contents
        assert "job-1" in manager.get_running_schedules()
        assert "job-2" in manager.get_running_schedules()
