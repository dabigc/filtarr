"""Extended tests for state management edge cases."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from filtarr.state import (
    BatchProgress,
    StateFile,
    StateManager,
)


class TestStateFileFromDictEdgeCases:
    """Tests for StateFile.from_dict() edge cases."""

    def test_from_dict_with_non_integer_version(self) -> None:
        """Should default to STATE_VERSION when version is not an integer."""
        from filtarr.state import STATE_VERSION

        data = {"version": "invalid", "checks": {}}
        state = StateFile.from_dict(data)

        assert state.version == STATE_VERSION

    def test_from_dict_with_missing_version(self) -> None:
        """Should default to STATE_VERSION when version is missing."""
        from filtarr.state import STATE_VERSION

        data = {"checks": {}}
        state = StateFile.from_dict(data)

        assert state.version == STATE_VERSION

    def test_from_dict_with_float_version(self) -> None:
        """Should default to STATE_VERSION when version is a float."""
        from filtarr.state import STATE_VERSION

        data = {"version": 2.5, "checks": {}}
        state = StateFile.from_dict(data)

        # Float is not an int, so should default
        assert state.version == STATE_VERSION

    def test_from_dict_with_checks_data_not_dict(self) -> None:
        """Should handle checks_data not being a dict."""
        data = {"checks": "not a dict"}
        state = StateFile.from_dict(data)

        assert state.checks == {}

    def test_from_dict_with_checks_data_as_list(self) -> None:
        """Should handle checks_data being a list."""
        data = {"checks": ["item1", "item2"]}
        state = StateFile.from_dict(data)

        assert state.checks == {}

    def test_from_dict_with_checks_data_as_none(self) -> None:
        """Should handle checks_data being None."""
        data = {"checks": None}
        state = StateFile.from_dict(data)

        assert state.checks == {}

    def test_from_dict_with_batch_progress_containing_invalid_data(self) -> None:
        """Should handle batch_progress with completely invalid data."""
        data = {
            "batch_progress": {
                "batch_id": 12345,  # Not a string
                "item_type": {"nested": "dict"},  # Not a valid type
                "total_items": "many",  # Not a number
                "processed_ids": {"set": "like"},  # Not a list
                "started_at": 12345,  # Not a string
            }
        }
        state = StateFile.from_dict(data)

        assert state.batch_progress is not None
        assert state.batch_progress.batch_id == "12345"  # Converted to string
        assert state.batch_progress.item_type == "mixed"  # Default for invalid
        assert state.batch_progress.total_items == 0  # Default for invalid
        assert state.batch_progress.processed_ids == set()  # Default for invalid

    def test_from_dict_with_dynamic_schedules_not_list(self) -> None:
        """Should handle dynamic_schedules not being a list."""
        data = {"dynamic_schedules": "not a list"}
        state = StateFile.from_dict(data)

        assert state.dynamic_schedules == []

    def test_from_dict_with_dynamic_schedules_as_dict(self) -> None:
        """Should handle dynamic_schedules being a dict."""
        data = {"dynamic_schedules": {"key": "value"}}
        state = StateFile.from_dict(data)

        assert state.dynamic_schedules == []

    def test_from_dict_with_dynamic_schedules_containing_non_dict_items(self) -> None:
        """Should filter out non-dict items from dynamic_schedules."""
        data = {
            "dynamic_schedules": [
                {"name": "valid_schedule"},
                "string_item",
                123,
                None,
                ["list_item"],
                {"name": "another_valid"},
            ]
        }
        state = StateFile.from_dict(data)

        assert len(state.dynamic_schedules) == 2
        assert state.dynamic_schedules[0] == {"name": "valid_schedule"}
        assert state.dynamic_schedules[1] == {"name": "another_valid"}

    def test_from_dict_with_schedule_history_not_list(self) -> None:
        """Should handle schedule_history not being a list."""
        data = {"schedule_history": "not a list"}
        state = StateFile.from_dict(data)

        assert state.schedule_history == []

    def test_from_dict_with_schedule_history_as_int(self) -> None:
        """Should handle schedule_history being an integer."""
        data = {"schedule_history": 42}
        state = StateFile.from_dict(data)

        assert state.schedule_history == []

    def test_from_dict_with_schedule_history_containing_non_dict_items(self) -> None:
        """Should filter out non-dict items from schedule_history."""
        data = {
            "schedule_history": [
                {"schedule_name": "run1", "started_at": "2024-01-01"},
                "string_item",
                456,
                None,
                True,
                {"schedule_name": "run2", "started_at": "2024-01-02"},
            ]
        }
        state = StateFile.from_dict(data)

        assert len(state.schedule_history) == 2
        assert state.schedule_history[0]["schedule_name"] == "run1"
        assert state.schedule_history[1]["schedule_name"] == "run2"

    def test_from_dict_with_checks_containing_non_dict_record(self) -> None:
        """Should skip non-dict records in checks."""
        data = {
            "checks": {
                "movie:1": {
                    "last_checked": datetime.now(UTC).isoformat(),
                    "result": "available",
                },
                "movie:2": "not a dict",
                "movie:3": 123,
                "movie:4": None,
            }
        }
        state = StateFile.from_dict(data)

        # Only movie:1 should be loaded
        assert state.get_check("movie", 1) is not None
        assert state.get_check("movie", 2) is None
        assert state.get_check("movie", 3) is None
        assert state.get_check("movie", 4) is None


class TestStateManagerEdgeCases:
    """Tests for StateManager edge cases."""

    def test_save_when_state_is_none(self, tmp_path: Path) -> None:
        """Should return early when _state is None."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # _state is None initially (not loaded yet)
        manager.save()

        # File should not be created since save returned early
        assert not state_path.exists()

    def test_update_schedule_run_when_record_not_found(self, tmp_path: Path) -> None:
        """Should return False when schedule run record is not found."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        # Load state to initialize
        manager.load()

        # Add a history record
        manager.add_schedule_run(
            {
                "schedule_name": "test_schedule",
                "started_at": "2024-01-01T12:00:00Z",
                "status": "running",
            }
        )

        # Try to update a non-existent record (different schedule_name)
        result = manager.update_schedule_run(
            schedule_name="different_schedule",
            started_at="2024-01-01T12:00:00Z",
            updates={"status": "completed"},
        )

        assert result is False

    def test_update_schedule_run_when_started_at_not_matching(self, tmp_path: Path) -> None:
        """Should return False when started_at doesn't match."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()
        manager.add_schedule_run(
            {
                "schedule_name": "test_schedule",
                "started_at": "2024-01-01T12:00:00Z",
                "status": "running",
            }
        )

        # Try to update with different started_at
        result = manager.update_schedule_run(
            schedule_name="test_schedule",
            started_at="2024-01-01T13:00:00Z",  # Different time
            updates={"status": "completed"},
        )

        assert result is False

    def test_update_schedule_run_success(self, tmp_path: Path) -> None:
        """Should return True and update when record is found."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()
        manager.add_schedule_run(
            {
                "schedule_name": "test_schedule",
                "started_at": "2024-01-01T12:00:00Z",
                "status": "running",
            }
        )

        # Update the record
        result = manager.update_schedule_run(
            schedule_name="test_schedule",
            started_at="2024-01-01T12:00:00Z",
            updates={"status": "completed", "ended_at": "2024-01-01T12:30:00Z"},
        )

        assert result is True

        # Verify the update
        history = manager.get_schedule_history(schedule_name="test_schedule")
        assert len(history) == 1
        assert history[0]["status"] == "completed"
        assert history[0]["ended_at"] == "2024-01-01T12:30:00Z"

    def test_prune_schedule_history_when_smaller_than_limit(self, tmp_path: Path) -> None:
        """Should return 0 when history is smaller than limit."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        # Add a few history records
        for i in range(3):
            manager.add_schedule_run(
                {
                    "schedule_name": f"schedule_{i}",
                    "started_at": f"2024-01-0{i + 1}T12:00:00Z",
                }
            )

        # Try to prune with limit higher than current count
        removed = manager.prune_schedule_history(limit=10)

        assert removed == 0

    def test_prune_schedule_history_when_equal_to_limit(self, tmp_path: Path) -> None:
        """Should return 0 when history is exactly equal to limit."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        for i in range(5):
            manager.add_schedule_run(
                {
                    "schedule_name": f"schedule_{i}",
                    "started_at": f"2024-01-0{i + 1}T12:00:00Z",
                }
            )

        removed = manager.prune_schedule_history(limit=5)

        assert removed == 0

    def test_prune_schedule_history_removes_oldest(self, tmp_path: Path) -> None:
        """Should remove oldest entries when pruning."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        for i in range(5):
            manager.add_schedule_run(
                {
                    "schedule_name": f"schedule_{i}",
                    "started_at": f"2024-01-0{i + 1}T12:00:00Z",
                }
            )

        removed = manager.prune_schedule_history(limit=2)

        assert removed == 3
        # Get history (returns most recent first)
        history = manager.get_schedule_history()
        assert len(history) == 2
        # Most recent (schedule_4) should be first
        assert history[0]["schedule_name"] == "schedule_4"
        assert history[1]["schedule_name"] == "schedule_3"

    def test_get_dynamic_schedule_when_not_found(self, tmp_path: Path) -> None:
        """Should return None when schedule is not found."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        # Add one schedule
        manager.add_dynamic_schedule({"name": "existing_schedule", "cron": "0 0 * * *"})

        # Try to get a non-existent schedule
        result = manager.get_dynamic_schedule("nonexistent_schedule")

        assert result is None

    def test_get_dynamic_schedule_case_insensitive(self, tmp_path: Path) -> None:
        """Should find schedule case-insensitively."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()
        manager.add_dynamic_schedule({"name": "MySchedule", "cron": "0 0 * * *"})

        # Find with different case
        result = manager.get_dynamic_schedule("MYSCHEDULE")

        assert result is not None
        assert result["name"] == "MySchedule"

    def test_update_batch_progress_when_no_batch(self, tmp_path: Path) -> None:
        """Should do nothing when no batch is in progress."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        # Try to update without starting a batch
        manager.update_batch_progress(42)

        # Should not raise, and no batch should exist
        assert manager.get_batch_progress() is None


class TestBatchProgressFromDictEdgeCases:
    """Tests for BatchProgress.from_dict() edge cases."""

    def test_from_dict_with_invalid_item_type(self) -> None:
        """Should default to 'mixed' for invalid item_type values."""
        for invalid_type in ["invalid", "MOVIE", "Series", "", None, 123, True]:
            data = {"item_type": invalid_type}
            progress = BatchProgress.from_dict(data)
            assert progress.item_type == "mixed"

    def test_from_dict_with_non_integer_total_items(self) -> None:
        """Should default to 0 for non-integer total_items."""
        test_cases = [
            ("not a number", 0),
            (None, 0),
            ({"nested": "dict"}, 0),
            (["list"], 0),
        ]

        for value, expected in test_cases:
            data = {"total_items": value}
            progress = BatchProgress.from_dict(data)
            assert progress.total_items == expected, f"Failed for {value}"

    def test_from_dict_with_bool_total_items(self) -> None:
        """Should handle bool total_items (bool is subclass of int in Python)."""
        # In Python, bool is a subclass of int, so True == 1 and False == 0
        data_true = {"total_items": True}
        progress_true = BatchProgress.from_dict(data_true)
        assert progress_true.total_items == 1

        data_false = {"total_items": False}
        progress_false = BatchProgress.from_dict(data_false)
        assert progress_false.total_items == 0

    def test_from_dict_with_float_total_items(self) -> None:
        """Should convert float total_items to int."""
        data = {"total_items": 15.7}
        progress = BatchProgress.from_dict(data)

        assert progress.total_items == 15

    def test_from_dict_with_negative_total_items(self) -> None:
        """Should handle negative total_items."""
        data = {"total_items": -5}
        progress = BatchProgress.from_dict(data)

        assert progress.total_items == -5

    def test_from_dict_with_mixed_processed_ids(self) -> None:
        """Should filter non-numeric values from processed_ids."""
        data = {"processed_ids": [1, 2.5, "string", None, 3, True, {"dict": True}]}
        progress = BatchProgress.from_dict(data)

        # Only numeric values should be kept (1, 2.5, 3)
        assert progress.processed_ids == {1, 2, 3}

    def test_from_dict_with_non_string_started_at(self) -> None:
        """Should use current time for non-string started_at."""
        data = {"started_at": 12345}  # Not a string
        before = datetime.now(UTC)
        progress = BatchProgress.from_dict(data)
        after = datetime.now(UTC)

        assert before <= progress.started_at <= after

    def test_from_dict_with_invalid_iso_started_at(self) -> None:
        """Should raise error for invalid ISO timestamp."""
        data = {"started_at": "not-a-valid-timestamp"}

        with pytest.raises(ValueError):
            BatchProgress.from_dict(data)


class TestStateManagerSchedulerOperations:
    """Tests for StateManager scheduler-related operations."""

    def test_add_dynamic_schedule_without_name(self, tmp_path: Path) -> None:
        """Should raise ValueError when schedule has no name."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        with pytest.raises(ValueError, match="must have a 'name' field"):
            manager.add_dynamic_schedule({"cron": "0 0 * * *"})

    def test_add_dynamic_schedule_with_empty_name(self, tmp_path: Path) -> None:
        """Should raise ValueError when schedule name is empty."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        with pytest.raises(ValueError, match="must have a 'name' field"):
            manager.add_dynamic_schedule({"name": "", "cron": "0 0 * * *"})

    def test_add_dynamic_schedule_replaces_existing(self, tmp_path: Path) -> None:
        """Should replace existing schedule with same name."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        # Add initial schedule
        manager.add_dynamic_schedule({"name": "test_schedule", "cron": "0 0 * * *"})

        # Add schedule with same name
        manager.add_dynamic_schedule(
            {"name": "test_schedule", "cron": "0 12 * * *", "new_field": "value"}
        )

        schedules = manager.get_dynamic_schedules()
        assert len(schedules) == 1
        assert schedules[0]["cron"] == "0 12 * * *"
        assert schedules[0]["new_field"] == "value"

    def test_remove_dynamic_schedule_not_found(self, tmp_path: Path) -> None:
        """Should return False when schedule to remove is not found."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()
        manager.add_dynamic_schedule({"name": "existing", "cron": "0 0 * * *"})

        result = manager.remove_dynamic_schedule("nonexistent")

        assert result is False

    def test_remove_dynamic_schedule_case_insensitive(self, tmp_path: Path) -> None:
        """Should remove schedule case-insensitively."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()
        manager.add_dynamic_schedule({"name": "TestSchedule", "cron": "0 0 * * *"})

        result = manager.remove_dynamic_schedule("testschedule")

        assert result is True
        assert len(manager.get_dynamic_schedules()) == 0

    def test_update_dynamic_schedule_not_found(self, tmp_path: Path) -> None:
        """Should return False when schedule to update is not found."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        result = manager.update_dynamic_schedule("nonexistent", {"enabled": False})

        assert result is False

    def test_update_dynamic_schedule_success(self, tmp_path: Path) -> None:
        """Should update schedule fields and return True."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()
        manager.add_dynamic_schedule(
            {"name": "test_schedule", "cron": "0 0 * * *", "enabled": True}
        )

        result = manager.update_dynamic_schedule(
            "test_schedule", {"enabled": False, "new_field": "added"}
        )

        assert result is True
        schedule = manager.get_dynamic_schedule("test_schedule")
        assert schedule is not None
        assert schedule["enabled"] is False
        assert schedule["new_field"] == "added"
        assert schedule["cron"] == "0 0 * * *"  # Original field preserved

    def test_get_schedule_history_filtered_by_name(self, tmp_path: Path) -> None:
        """Should filter history by schedule name."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        manager.add_schedule_run({"schedule_name": "schedule_a", "status": "completed"})
        manager.add_schedule_run({"schedule_name": "schedule_b", "status": "completed"})
        manager.add_schedule_run({"schedule_name": "schedule_a", "status": "completed"})

        history = manager.get_schedule_history(schedule_name="schedule_a")

        assert len(history) == 2
        for record in history:
            assert record["schedule_name"] == "schedule_a"

    def test_get_schedule_history_with_limit(self, tmp_path: Path) -> None:
        """Should limit history results."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        for i in range(5):
            manager.add_schedule_run({"schedule_name": f"schedule_{i}", "status": "completed"})

        history = manager.get_schedule_history(limit=3)

        assert len(history) == 3

    def test_get_schedule_history_most_recent_first(self, tmp_path: Path) -> None:
        """Should return history with most recent first."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()

        manager.add_schedule_run({"schedule_name": "first", "started_at": "2024-01-01T00:00:00Z"})
        manager.add_schedule_run({"schedule_name": "second", "started_at": "2024-01-02T00:00:00Z"})
        manager.add_schedule_run({"schedule_name": "third", "started_at": "2024-01-03T00:00:00Z"})

        history = manager.get_schedule_history()

        assert history[0]["schedule_name"] == "third"
        assert history[1]["schedule_name"] == "second"
        assert history[2]["schedule_name"] == "first"

    def test_update_schedule_run_case_insensitive(self, tmp_path: Path) -> None:
        """Should match schedule name case-insensitively."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        manager.load()
        manager.add_schedule_run(
            {
                "schedule_name": "TestSchedule",
                "started_at": "2024-01-01T12:00:00Z",
                "status": "running",
            }
        )

        result = manager.update_schedule_run(
            schedule_name="TESTSCHEDULE",
            started_at="2024-01-01T12:00:00Z",
            updates={"status": "completed"},
        )

        assert result is True
